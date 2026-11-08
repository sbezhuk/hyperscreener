import asyncio
import time
from typing import Dict, List, Any, Tuple, Optional
from ..hyperliquid import hl_client
from .trendline import detect_timeframe_trendlines

SUPPORTED_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]

HTF_TIMEFRAME_MAP: Dict[str, Optional[str]] = {
    "1m": "15m",
    "3m": "15m",
    "5m": "1h",
    "15m": "1h",
    "30m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": None,
}


class MTFTrendlineManager:
    """
    Independent Multi-Timeframe Trendline Engine with Structural Risk & HTF Context.
    - Strictly computes trendlines per timeframe from that timeframe's own candle history.
    - NO coordinate inheritance, scaling, or transfer between timeframes is permitted.
    - Evaluates HTF structural context strictly point-in-time from higher timeframe candles.
    - Caches per (coin, timeframe) with TTL to prevent re-computation while ensuring isolation.
    """

    def __init__(self, cache_ttl_seconds: float = 60.0):
        self._cache_ttl = cache_ttl_seconds
        # key: (coin, tf) -> { "trendlines": [...], "timestamp": float, "last_candle_time": int }
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # key: (coin, tf) -> { "candles": [...], "timestamp": float }
        self._candle_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

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

    def get_cached_candles(self, coin: str, tf: str) -> Optional[List[Dict[str, Any]]]:
        key = (coin.upper(), tf.lower())
        entry = self._candle_cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self._cache_ttl):
            return entry["candles"]
        return None

    def clear_cache(self, coin: Optional[str] = None, tf: Optional[str] = None) -> None:
        """Clears cache for tests or specific coin/tf."""
        if coin and tf:
            self._cache.pop((coin.upper(), tf.lower()), None)
            self._candle_cache.pop((coin.upper(), tf.lower()), None)
        elif coin:
            keys = [k for k in self._cache if k[0] == coin.upper()]
            for k in keys:
                self._cache.pop(k, None)
            c_keys = [k for k in self._candle_cache if k[0] == coin.upper()]
            for k in c_keys:
                self._candle_cache.pop(k, None)
        else:
            self._cache.clear()
            self._candle_cache.clear()

    async def get_all_timeframe_trendlines(
        self,
        coin: str,
        active_interval: str,
        active_candles: List[Dict[str, Any]],
        include_broken: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Analyzes and returns independent trendlines for ALL timeframes.
        Active timeframe is analyzed immediately with provided active_candles and HTF context.
        Other timeframes are retrieved from independent cache or fetched on-demand.
        """
        coin = coin.upper()
        clean_active_tf = active_interval.lower()

        # Cache active candles
        if active_candles:
            self._candle_cache[(coin, clean_active_tf)] = {
                "candles": active_candles,
                "timestamp": time.time(),
            }

        all_tf_tls: Dict[str, List[Dict[str, Any]]] = {}

        # 1. Determine which timeframes need candles fetched
        needed_tfs = [tf for tf in SUPPORTED_TIMEFRAMES if tf != clean_active_tf]
        missing_tfs = [tf for tf in needed_tfs if not self.get_cached_candles(coin, tf)]

        if missing_tfs:
            async def fetch_candles(tf: str):
                try:
                    c = await hl_client.get_candles(coin=coin, interval=tf, limit=300)
                    if c:
                        self._candle_cache[(coin, tf)] = {
                            "candles": c,
                            "timestamp": time.time(),
                        }
                except Exception:
                    pass

            await asyncio.gather(*(fetch_candles(tf) for tf in missing_tfs))

        # Helper to get HTF candles for a given TF
        def get_htf_candles_for_tf(tf: str) -> Optional[List[Dict[str, Any]]]:
            htf_tf = HTF_TIMEFRAME_MAP.get(tf)
            if not htf_tf:
                return None
            return self.get_cached_candles(coin, htf_tf)

        # 2. Process active timeframe with HTF structural context
        active_htf = get_htf_candles_for_tf(clean_active_tf)
        active_tls = detect_timeframe_trendlines(
            candles=active_candles,
            interval=clean_active_tf,
            include_broken=include_broken,
            htf_candles=active_htf,
        )
        last_time = active_candles[-1]["time"] if active_candles else 0
        self.store_cached_trendlines(coin, clean_active_tf, active_tls, last_time)
        all_tf_tls[clean_active_tf] = active_tls

        # 3. Retrieve or compute other timeframes
        for tf in needed_tfs:
            cached_tls = self.get_cached_trendlines(coin, tf)
            if cached_tls is not None:
                all_tf_tls[tf] = cached_tls
            else:
                tf_candles = self.get_cached_candles(coin, tf)
                if tf_candles:
                    htf_c = get_htf_candles_for_tf(tf)
                    detected = detect_timeframe_trendlines(
                        candles=tf_candles,
                        interval=tf,
                        include_broken=include_broken,
                        htf_candles=htf_c,
                    )
                    c_last = tf_candles[-1]["time"] if tf_candles else 0
                    self.store_cached_trendlines(coin, tf, detected, c_last)
                    all_tf_tls[tf] = detected
                else:
                    all_tf_tls[tf] = []

        return all_tf_tls


mtf_trendline_manager = MTFTrendlineManager()
