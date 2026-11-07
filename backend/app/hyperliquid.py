import asyncio
import time
from typing import List, Dict, Any, Optional
import httpx

HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"

class HyperliquidClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, float] = {}

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            self._client = httpx.AsyncClient(timeout=10.0, limits=limits)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_meta_and_contexts(self) -> List[Dict[str, Any]]:
        """
        Fetches all active perps on Hyperliquid with mark price, 24h volume, OI, and funding.
        Cached for 10 seconds.
        """
        cache_key = "metaAndAssetCtxs"
        now = time.time()
        if cache_key in self._cache and self._cache_expiry.get(cache_key, 0) > now:
            return self._cache[cache_key]

        client = await self.get_client()
        payload = {"type": "metaAndAssetCtxs"}
        
        for attempt in range(3):
            try:
                resp = await client.post(HYPERLIQUID_API_URL, json=payload)
                if resp.status_code == 429:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == 2:
                    if cache_key in self._cache:
                        return self._cache[cache_key]
                    raise e
                await asyncio.sleep(0.5 * (2 ** attempt))
        else:
            if cache_key in self._cache:
                return self._cache[cache_key]
            return []
        
        meta = data[0]["universe"]
        ctxs = data[1]
        
        coins = []
        for universe_item, ctx in zip(meta, ctxs):
            if universe_item.get("isDelisted"):
                continue
            
            name = universe_item["name"]
            mark_px = float(ctx.get("markPx", 0.0))
            day_volume = float(ctx.get("dayNtlVlm", 0.0))
            prev_day_px = float(ctx.get("prevDayPx", mark_px))
            change_24h = ((mark_px - prev_day_px) / prev_day_px * 100) if prev_day_px > 0 else 0.0
            open_interest = float(ctx.get("openInterest", 0.0))
            funding = float(ctx.get("funding", 0.0))
            
            coins.append({
                "name": name,
                "markPrice": mark_px,
                "volume24h": day_volume,
                "change24h": round(change_24h, 2),
                "openInterest": open_interest,
                "fundingRate": funding,
                "szDecimals": universe_item.get("szDecimals", 2)
            })

            # Track in OITracker
            try:
                from .analyzer.oi_tracker import oi_manager
                if open_interest > 0 and mark_px > 0:
                    oi_manager.record_tick(coin=name, oi=open_interest, price=mark_px)
            except Exception:
                pass
            
        coins.sort(key=lambda x: x["volume24h"], reverse=True)
        self._cache[cache_key] = coins
        self._cache_expiry[cache_key] = now + 10.0
        return coins

    async def get_candles(
        self,
        coin: str,
        interval: str = "5m",
        limit: int = 1000,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches historical OHLCV candles from Hyperliquid.
        Normalized and cached for fast responsiveness.
        Supports custom start_time and end_time (in milliseconds).
        """
        coin = coin.upper()
        # Normalization: e.g. '1D' -> '1d'
        interval_clean = interval.lower()
        if interval_clean not in ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d"]:
            interval_clean = "5m"

        cache_key = f"candles:{coin}:{interval_clean}:{limit}:{start_time}:{end_time}"
        now = time.time()
        if cache_key in self._cache and self._cache_expiry.get(cache_key, 0) > now:
            return self._cache[cache_key]

        client = await self.get_client()
        
        interval_ms_map = {
            "1m": 60 * 1000,
            "3m": 3 * 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "2h": 2 * 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "8h": 8 * 60 * 60 * 1000,
            "12h": 12 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }
        
        step = interval_ms_map.get(interval_clean, 5 * 60 * 1000)
        now_ms = int(time.time() * 1000)
        end_ms = end_time if end_time is not None else now_ms
        start_ms = start_time if start_time is not None else (end_ms - (limit * step))
        
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval_clean,
                "startTime": start_ms,
                "endTime": end_ms
            }
        }
        
        # Retry up to 4 times on 429 rate limit with backoff
        for attempt in range(4):
            try:
                resp = await client.post(HYPERLIQUID_API_URL, json=payload)
                if resp.status_code == 429:
                    wait_time = 0.8 * (1.5 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                resp.raise_for_status()
                raw_candles = resp.json()
                break
            except Exception as e:
                if attempt == 3:
                    if cache_key in self._cache:
                        return self._cache[cache_key]
                    raise e
                await asyncio.sleep(0.8 * (1.5 ** attempt))
        else:
            if cache_key in self._cache:
                return self._cache[cache_key]
            # Try any matching coin and interval from cache as fallback
            for k, val in self._cache.items():
                if k.startswith(f"candles:{coin}:{interval_clean}:") and val:
                    return val
            return []
        
        candles = []
        for c in raw_candles:
            candles.append({
                "time": int(c["t"] / 1000),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c["v"])
            })
            
        candles.sort(key=lambda x: x["time"])
        
        self._cache[cache_key] = candles
        # Cache for 30s for general calls, longer if historical range (end_time set)
        ttl = 120.0 if end_time and end_time < now_ms - 60000 else 30.0
        self._cache_expiry[cache_key] = now + ttl
        return candles

hl_client = HyperliquidClient()
