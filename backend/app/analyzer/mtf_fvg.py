import asyncio
import time
from typing import Dict, List, Any, Tuple, Optional
from ..hyperliquid import hl_client
from .fvg import detect_fvgs, compute_mtf_confluences

# Supported timeframes as required by task
SUPPORTED_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]

class MTFFVGManager:
    """
    Independent Multi-Timeframe FVG Engine & Confluence Manager.
    - Each timeframe calculates its own independent FVGs based strictly on its own candles.
    - NO HTF Fallback is used: 1D uses 1D, 4H uses 4H, etc.
    - Caches per (coin, timeframe) with TTL to ensure high performance and no lag.
    - Tracks MTF Confluence across independent timeframes without merging original FVG objects.
    """

    def __init__(self, cache_ttl_seconds: float = 60.0):
        self._cache_ttl = cache_ttl_seconds
        # key: (coin, tf) -> { "fvgs": [...], "timestamp": float, "last_candle_time": int }
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_cached_fvgs(self, coin: str, tf: str) -> Optional[List[Dict[str, Any]]]:
        key = (coin.upper(), tf.lower())
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self._cache_ttl):
            return entry["fvgs"]
        return None

    def store_cached_fvgs(self, coin: str, tf: str, fvgs: List[Dict[str, Any]], last_candle_time: int = 0):
        key = (coin.upper(), tf.lower())
        self._cache[key] = {
            "fvgs": fvgs,
            "timestamp": time.time(),
            "last_candle_time": last_candle_time,
        }

    async def get_all_timeframe_fvgs(
        self,
        coin: str,
        active_interval: str,
        active_candles: List[Dict[str, Any]],
        trend: str = "NEUTRAL",
        structure_events: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes and returns independent FVGs for each timeframe and computes MTF Confluences.
        """
        coin = coin.upper()
        clean_active_tf = active_interval.lower()

        # 1. Process active timeframe immediately
        active_fvgs = detect_fvgs(active_candles, interval=clean_active_tf, symbol=coin)
        last_time = active_candles[-1]["time"] if active_candles else 0
        self.store_cached_fvgs(coin, clean_active_tf, active_fvgs, last_time)

        all_tf_fvgs: Dict[str, List[Dict[str, Any]]] = {}
        all_tf_fvgs[clean_active_tf] = active_fvgs

        # 2. Check cached or needed other timeframes
        needed_tfs = []
        for tf in SUPPORTED_TIMEFRAMES:
            if tf == clean_active_tf:
                continue
            cached = self.get_cached_fvgs(coin, tf)
            if cached is not None:
                all_tf_fvgs[tf] = cached
            else:
                needed_tfs.append(tf)

        # 3. Fetch missing timeframes concurrently
        if needed_tfs:
            async def fetch_and_analyze(tf: str):
                try:
                    c = await hl_client.get_candles(coin=coin, interval=tf, limit=300)
                    if c:
                        detected = detect_fvgs(c, interval=tf, symbol=coin)
                        self.store_cached_fvgs(coin, tf, detected, c[-1]["time"])
                        return tf, detected
                except Exception:
                    pass
                return tf, []

            results = await asyncio.gather(*(fetch_and_analyze(tf) for tf in needed_tfs))
            for tf, tf_fvgs in results:
                all_tf_fvgs[tf] = tf_fvgs

        # 4. Compute Multi-Timeframe Confluence zones
        confluences = compute_mtf_confluences(all_tf_fvgs, min_overlapping_tfs=2)

        return {
            "all_timeframes": all_tf_fvgs,
            "confluences": confluences,
            "active_fvgs": active_fvgs,
        }

mtf_fvg_manager = MTFFVGManager()
