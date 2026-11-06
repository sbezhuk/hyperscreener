import asyncio
import time
from typing import Dict, List, Any, Tuple
from ..hyperliquid import hl_client
from .levels import analyze_levels

ALL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

class MTFLevelsManager:
    """
    Independent Multi-Timeframe Support & Resistance Engine.
    - Maintains independent levels calculation and history for each timeframe.
    - Caches results per (coin, timeframe) with TTL to prevent re-computation.
    - Detects Multi-Timeframe Confluence Zones across timeframes.
    """

    def __init__(self, cache_ttl_seconds: float = 12.0):
        self._cache_ttl = cache_ttl_seconds
        # key: (coin, tf) -> { "levels": {...}, "timestamp": float, "last_candle_time": int }
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_cached_levels(self, coin: str, tf: str) -> Dict[str, Any] | None:
        key = (coin.upper(), tf.lower())
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self._cache_ttl):
            return entry["levels"]
        return None

    def store_cached_levels(self, coin: str, tf: str, levels: Dict[str, Any], last_candle_time: int = 0):
        key = (coin.upper(), tf.lower())
        self._cache[key] = {
            "levels": levels,
            "timestamp": time.time(),
            "last_candle_time": last_candle_time,
        }

    async def get_all_timeframe_levels(
        self,
        coin: str,
        current_price: float,
        active_interval: str,
        active_candles: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Analyzes and returns independent levels for ALL timeframes.
        Uses in-memory cache to guarantee fast response without redundant calculations.
        """
        coin = coin.upper()
        clean_active_tf = active_interval.lower()

        # 1. First, process the active timeframe's candles immediately
        active_levels = analyze_levels(active_candles, interval=clean_active_tf)
        last_time = active_candles[-1]["time"] if active_candles else 0
        self.store_cached_levels(coin, clean_active_tf, active_levels, last_time)

        # 2. Check which other timeframes need calculation
        needed_tfs = []
        mtf_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

        for tf in ALL_TIMEFRAMES:
            if tf == clean_active_tf:
                mtf_results[tf] = {
                    "resistances": active_levels.get("resistances", []),
                    "supports": active_levels.get("supports", []),
                }
            else:
                cached = self.get_cached_levels(coin, tf)
                if cached:
                    mtf_results[tf] = {
                        "resistances": cached.get("resistances", []),
                        "supports": cached.get("supports", []),
                    }
                else:
                    needed_tfs.append(tf)

        # 3. Fetch and analyze any expired / missing timeframes concurrently
        if needed_tfs:
            async def fetch_and_analyze(tf: str):
                try:
                    c = await hl_client.get_candles(coin=coin, interval=tf, limit=300)
                    if c:
                        lvl = analyze_levels(c, interval=tf)
                        c_last = c[-1]["time"]
                        self.store_cached_levels(coin, tf, lvl, c_last)
                        return tf, {
                            "resistances": lvl.get("resistances", []),
                            "supports": lvl.get("supports", []),
                        }
                except Exception:
                    pass
                return tf, {"resistances": [], "supports": []}

            results = await asyncio.gather(*[fetch_and_analyze(tf) for tf in needed_tfs])
            for tf, res in results:
                mtf_results[tf] = res

        return mtf_results


mtf_levels_manager = MTFLevelsManager()
