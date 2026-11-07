import asyncio
import time
from typing import Dict, List, Any, Tuple, Optional
from ..hyperliquid import hl_client
from .trendline import detect_timeframe_trendlines

SUPPORTED_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]


class MTFTrendlineManager:
    """
    Independent Multi-Timeframe Trendline Engine.
    - Strictly computes trendlines per timeframe from that timeframe's own candle history.
    - NO coordinate inheritance, scaling, or transfer between timeframes is permitted.
    - Caches per (coin, timeframe) with TTL to prevent re-computation while ensuring isolation.
    """

    def __init__(self, cache_ttl_seconds: float = 60.0):
        self._cache_ttl = cache_ttl_seconds
        # key: (coin, tf) -> { "trendlines": [...], "timestamp": float, "last_candle_time": int }
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_cached_trendlines(self, coin: str, tf: str) -> Optional[List[Dict[str, Any]]]:
        key = (coin.upper(), tf.lower())
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self._cache_ttl):
            return entry["trendlines"]
        return None

    def store_cached_trendlines(
        self,
        coin: str,
        tf: str,
        trendlines: List[Dict[str, Any]],
        last_candle_time: int = 0,
    ) -> None:
        key = (coin.upper(), tf.lower())
        self._cache[key] = {
            "trendlines": trendlines,
            "timestamp": time.time(),
            "last_candle_time": last_candle_time,
        }

    def clear_cache(self, coin: Optional[str] = None, tf: Optional[str] = None) -> None:
        """Clears cache for tests or specific coin/tf."""
        if coin and tf:
            self._cache.pop((coin.upper(), tf.lower()), None)
        elif coin:
            keys = [k for k in self._cache if k[0] == coin.upper()]
            for k in keys:
                self._cache.pop(k, None)
        else:
            self._cache.clear()

    async def get_all_timeframe_trendlines(
        self,
        coin: str,
        active_interval: str,
        active_candles: List[Dict[str, Any]],
        include_broken: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Analyzes and returns independent trendlines for ALL timeframes.
        Active timeframe is analyzed immediately with provided active_candles.
        Other timeframes are retrieved from independent cache or fetched on-demand.
        """
        coin = coin.upper()
        clean_active_tf = active_interval.lower()

        # 1. Process active timeframe immediately strictly from active candles
        active_tls = detect_timeframe_trendlines(
            candles=active_candles,
            interval=clean_active_tf,
            include_broken=include_broken,
        )
        last_time = active_candles[-1]["time"] if active_candles else 0
        self.store_cached_trendlines(coin, clean_active_tf, active_tls, last_time)

        all_tf_tls: Dict[str, List[Dict[str, Any]]] = {
            clean_active_tf: active_tls
        }

        # 2. Check which other timeframes need calculation
        needed_tfs: List[str] = []
        for tf in SUPPORTED_TIMEFRAMES:
            if tf == clean_active_tf:
                continue
            cached = self.get_cached_trendlines(coin, tf)
            if cached is not None:
                all_tf_tls[tf] = cached
            else:
                needed_tfs.append(tf)

        # 3. Fetch missing timeframes independently in parallel
        if needed_tfs:
            async def fetch_and_analyze(tf: str):
                try:
                    c = await hl_client.get_candles(coin=coin, interval=tf, limit=300)
                    if c:
                        detected = detect_timeframe_trendlines(
                            candles=c,
                            interval=tf,
                            include_broken=include_broken,
                        )
                        c_last = c[-1]["time"] if c else 0
                        self.store_cached_trendlines(coin, tf, detected, c_last)
                        return tf, detected
                except Exception:
                    pass
                return tf, []

            results = await asyncio.gather(*(fetch_and_analyze(tf) for tf in needed_tfs))
            for tf, tls in results:
                all_tf_tls[tf] = tls

        return all_tf_tls


mtf_trendline_manager = MTFTrendlineManager()
