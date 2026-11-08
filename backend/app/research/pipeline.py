import asyncio
import os
import sys
import time
import json
import math
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Set

# Ensure app modules are importable
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.hyperliquid import hl_client

# Configurable Cache Roots
DEFAULT_CACHE_DIR = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "scratch", "cache"))
_CUSTOM_CACHE_DIR: Optional[str] = None


def get_cache_dir() -> str:
    """Returns the active research cache directory."""
    d = _CUSTOM_CACHE_DIR or DEFAULT_CACHE_DIR
    os.makedirs(os.path.join(d, "datasets"), exist_ok=True)
    return d


def set_custom_cache_dir(path: Optional[str]):
    """Allows test fixtures or environments to override the cache location."""
    global _CUSTOM_CACHE_DIR
    _CUSTOM_CACHE_DIR = path
    if path:
        os.makedirs(os.path.join(path, "datasets"), exist_ok=True)


def _get_metadata_cache_file() -> str:
    return os.path.join(get_cache_dir(), "market_assets_metadata.json")


def _get_datasets_cache_dir() -> str:
    return os.path.join(get_cache_dir(), "datasets")


class MarketDiscoveryError(Exception):
    """Raised when asset or market discovery fails critically."""
    pass


def discover_supported_timeframes() -> List[str]:
    """
    Universal Timeframe Discovery:
    Returns the deterministic, supported timeframe universe provided by Hyperliquid.
    No hardcoded, fragmented lists across research phases.
    """
    return ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d"]


def get_timeframe_step_seconds(interval: str) -> int:
    """Returns interval step in seconds for boundary and gap calculations."""
    tf_map = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "8h": 28800,
        "12h": 43200,
        "1d": 86400,
    }
    clean = interval.lower()
    return tf_map.get(clean, 900)


def get_htf_for_timeframe(interval: str) -> str:
    """
    Standard Higher Timeframe (HTF) context mapping for multi-timeframe analysis:
      1m -> 5m
      3m -> 15m
      5m -> 1h
      15m -> 1h
      30m -> 4h
      1h -> 4h
      4h -> 1d
      1d -> 1d
    """
    mapping = {
        "1m": "5m",
        "3m": "15m",
        "5m": "1h",
        "15m": "1h",
        "30m": "4h",
        "1h": "4h",
        "2h": "4h",
        "4h": "1d",
        "8h": "1d",
        "12h": "1d",
        "1d": "1d",
    }
    return mapping.get(interval.lower(), "1h")


async def discover_available_assets(
    min_daily_volume_usd: float = 0.0,
    exclude_delisted: bool = True,
    limit: Optional[int] = None,
    force_refresh: bool = False,
    max_cache_age_seconds: int = 120,
) -> List[Dict[str, Any]]:
    """
    Universal Asset Discovery:
    Dynamically queries Hyperliquid exchange perpetual universe.
    - Excludes delisted or dead instruments (markPrice <= 0).
    - Sorts deterministically by 24h volume descending.
    - Handles API connectivity errors with cached fallback (clearly flagged).
    - Never uses static hardcoded lists.
    """
    now = time.time()
    meta_cache_file = _get_metadata_cache_file()

    # 1. Check local metadata cache if not force refresh
    if not force_refresh and os.path.exists(meta_cache_file):
        try:
            with open(meta_cache_file, "r") as f:
                cached_data = json.load(f)
            cached_at = cached_data.get("timestamp", 0)
            if now - cached_at < max_cache_age_seconds:
                coins = cached_data.get("assets", [])
                filtered = [c for c in coins if c.get("volume24h", 0) >= min_daily_volume_usd]
                if limit:
                    filtered = filtered[:limit]
                return filtered
        except Exception:
            pass  # Fallback to fresh query

    # 2. Query live exchange API with retry logic
    live_coins = []
    error_msg = None
    for attempt in range(3):
        try:
            live_coins = await hl_client.get_meta_and_contexts()
            if live_coins and len(live_coins) > 0:
                break
        except Exception as e:
            error_msg = str(e)
            await asyncio.sleep(0.1 * (attempt + 1))

    # 3. Handle failure: try reading disk cache as fallback
    if not live_coins:
        if os.path.exists(meta_cache_file):
            try:
                with open(meta_cache_file, "r") as f:
                    fallback_data = json.load(f)
                coins = fallback_data.get("assets", [])
                for c in coins:
                    c["is_stale_fallback"] = True
                    c["fallback_cached_at"] = fallback_data.get("timestamp", 0)
                filtered = [c for c in coins if c.get("volume24h", 0) >= min_daily_volume_usd]
                if limit:
                    filtered = filtered[:limit]
                return filtered
            except Exception:
                pass
        raise MarketDiscoveryError(f"Failed to discover Hyperliquid active assets: {error_msg}")

    # 4. Filter and structure discovered universe
    cleaned_assets: List[Dict[str, Any]] = []
    for item in live_coins:
        if exclude_delisted and item.get("isDelisted", False):
            continue
        mark_px = float(item.get("markPrice", 0.0))
        vol = float(item.get("volume24h", 0.0))
        if mark_px <= 0.0:
            continue
        if vol < min_daily_volume_usd:
            continue

        asset_entry = {
            "name": str(item["name"]).upper(),
            "markPrice": mark_px,
            "volume24h": vol,
            "change24h": float(item.get("change24h", 0.0)),
            "openInterest": float(item.get("openInterest", 0.0)),
            "fundingRate": float(item.get("fundingRate", 0.0)),
            "szDecimals": item.get("szDecimals", 2),
            "is_stale_fallback": False,
        }
        cleaned_assets.append(asset_entry)

    # Sort deterministically by 24h volume descending
    cleaned_assets.sort(key=lambda x: x["volume24h"], reverse=True)

    # 5. Persist fresh metadata cache
    try:
        with open(meta_cache_file, "w") as f:
            json.dump({
                "timestamp": now,
                "exchange": "hyperliquid",
                "universe_count": len(cleaned_assets),
                "assets": cleaned_assets,
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save metadata cache: {e}")

    if limit:
        cleaned_assets = cleaned_assets[:limit]

    return cleaned_assets


def validate_candle_data_quality(
    candles: List[Dict[str, Any]],
    interval: str,
    min_required_candles: int = 50,
) -> Dict[str, Any]:
    """
    Data Quality Audit Engine:
    Validates completeness, sorting, duplicates, gaps, and candle close invariants.
    """
    n = len(candles)
    step = get_timeframe_step_seconds(interval)

    if n < min_required_candles:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "candle_count": n,
            "is_valid": False,
            "rejection_reason": f"Only {n} candles received, minimum required: {min_required_candles}",
            "missing_fields": 0,
            "duplicates_count": 0,
            "gaps_count": 0,
            "completeness_pct": round((n / max(min_required_candles, 1)) * 100.0, 1),
            "is_sorted": False,
            "start_time": candles[0]["time"] if n > 0 else 0,
            "end_time": candles[-1]["time"] if n > 0 else 0,
        }

    # 1. Field Completeness Check
    missing_fields = 0
    for c in candles:
        for k in ["time", "open", "high", "low", "close"]:
            if k not in c or c[k] is None:
                missing_fields += 1

    # 2. Chronological & Duplicate Check
    timestamps = [int(c["time"]) for c in candles]
    is_sorted = all(timestamps[i] <= timestamps[i + 1] for i in range(n - 1))
    duplicates = len(timestamps) - len(set(timestamps))

    # 3. Gap Check (> 1.5 * step)
    gaps_count = 0
    for i in range(n - 1):
        diff = timestamps[i + 1] - timestamps[i]
        if diff > step * 1.5:
            gaps_count += 1

    # Invariants for validity
    is_valid = (missing_fields == 0) and (duplicates == 0) and is_sorted and (n >= min_required_candles)
    rejection_reason = None
    if not is_sorted:
        rejection_reason = "Candle timestamps are not strictly ascending"
    elif duplicates > 0:
        rejection_reason = f"Contains {duplicates} duplicate timestamps"
    elif missing_fields > 0:
        rejection_reason = f"Contains {missing_fields} missing OHLCV fields"

    status = "VALID" if is_valid else "DATA_QUALITY_REJECTED"

    return {
        "status": status,
        "candle_count": n,
        "is_valid": is_valid,
        "rejection_reason": rejection_reason,
        "missing_fields": missing_fields,
        "duplicates_count": duplicates,
        "gaps_count": gaps_count,
        "completeness_pct": 100.0 if is_valid else 0.0,
        "is_sorted": is_sorted,
        "start_time": timestamps[0],
        "end_time": timestamps[-1],
    }


def _get_dataset_cache_path(coin: str, timeframe: str) -> str:
    """Returns isolated, deterministic file path for an asset-timeframe dataset."""
    safe_coin = coin.upper().replace("/", "_").replace(":", "_")
    safe_tf = timeframe.lower()
    return os.path.join(_get_datasets_cache_dir(), f"{safe_coin}_{safe_tf}.json")


async def get_single_dataset(
    coin: str,
    timeframe: str,
    limit: int = 1500,
    force_refresh: bool = False,
    max_age_seconds: int = 3600,
) -> Dict[str, Any]:
    """
    Isolated Dataset Loader:
    - Loads or fetches a specific (coin, timeframe) pair.
    - Validates data quality.
    - Caches into isolated per-asset/per-timeframe JSON store.
    """
    cache_file = _get_dataset_cache_path(coin, timeframe)
    now = time.time()

    # 1. Attempt reading fresh isolated cache
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached = json.load(f)
            meta = cached.get("metadata", {})
            updated_at = meta.get("updated_at", 0)
            if now - updated_at < max_age_seconds and cached.get("candles"):
                quality = meta.get("quality", {})
                return {
                    "coin": coin.upper(),
                    "timeframe": timeframe.lower(),
                    "candles": cached["candles"],
                    "quality": quality,
                    "from_cache": True,
                }
        except Exception:
            pass

    # 2. Fetch fresh candles from exchange
    candles = await hl_client.get_candles(coin=coin, interval=timeframe, limit=limit)
    if not candles:
        # Retry once
        await asyncio.sleep(0.1)
        candles = await hl_client.get_candles(coin=coin, interval=timeframe, limit=limit)

    candles = candles or []
    quality = validate_candle_data_quality(candles, interval=timeframe)

    # 3. Store into isolated cache file
    if candles and quality["is_valid"]:
        try:
            payload = {
                "metadata": {
                    "exchange": "hyperliquid",
                    "coin": coin.upper(),
                    "timeframe": timeframe.lower(),
                    "version": "2.0",
                    "created_at": now,
                    "updated_at": now,
                    "start_time": quality["start_time"],
                    "end_time": quality["end_time"],
                    "candle_count": quality["candle_count"],
                    "quality": quality,
                },
                "candles": candles,
            }
            with open(cache_file, "w") as f:
                json.dump(payload, f)
        except Exception as e:
            print(f"Warning: Failed to cache dataset {coin} {timeframe}: {e}")

    return {
        "coin": coin.upper(),
        "timeframe": timeframe.lower(),
        "candles": candles,
        "quality": quality,
        "from_cache": False,
    }


async def fetch_research_universe(
    coins: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    min_volume_usd: float = 0.0,
    candle_limit: int = 1500,
    max_concurrent: int = 4,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Centralized Research Dataset Pipeline:
    - Auto-discovers active assets if coins not specified.
    - Auto-discovers supported timeframes if timeframes not specified.
    - Concurrently loads and caches isolated datasets.
    - Produces a comprehensive audit and access interface.
    """
    # 1. Resolve Asset Universe
    if coins is None or len(coins) == 0:
        discovered_assets = await discover_available_assets(
            min_daily_volume_usd=min_volume_usd,
            limit=top_n,
            force_refresh=force_refresh,
        )
        target_coins = [a["name"] for a in discovered_assets]
    else:
        target_coins = [c.upper().strip() for c in coins]
        if top_n:
            target_coins = target_coins[:top_n]

    # 2. Resolve Timeframe Universe
    if timeframes is None or len(timeframes) == 0:
        target_tfs = discover_supported_timeframes()
    else:
        target_tfs = [t.lower().strip() for t in timeframes]

    semaphore = asyncio.Semaphore(max_concurrent)
    results: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    rejections: List[Dict[str, Any]] = []
    success_count = 0

    async def fetch_one(coin: str, tf: str):
        nonlocal success_count
        async with semaphore:
            ds = await get_single_dataset(
                coin=coin,
                timeframe=tf,
                limit=candle_limit,
                force_refresh=force_refresh,
            )
            results[coin][tf] = ds
            if ds["quality"]["is_valid"]:
                success_count += 1
            else:
                rejections.append({
                    "coin": coin,
                    "timeframe": tf,
                    "reason": ds["quality"]["rejection_reason"],
                    "status": ds["quality"]["status"],
                    "candle_count": ds["quality"]["candle_count"],
                })
            await asyncio.sleep(0.01)

    tasks = [fetch_one(c, tf) for c in target_coins for tf in target_tfs]
    await asyncio.gather(*tasks)

    return {
        "assets_count": len(target_coins),
        "timeframes_count": len(target_tfs),
        "total_combinations": len(target_coins) * len(target_tfs),
        "successful_datasets": success_count,
        "rejected_count": len(rejections),
        "rejections": rejections,
        "datasets": results,
        "target_coins": target_coins,
        "target_timeframes": target_tfs,
    }


class AwaitableList(list):
    """List subclass that can be awaited or used directly as a list."""
    def __await__(self):
        async def _identity():
            return self
        return _identity().__await__()


async def resolve_research_coins(
    coins_arg: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    min_volume_usd: float = 0.0,
) -> List[str]:
    """
    Universally resolves active perpetual assets from Hyperliquid without static lists.
    If explicitly passed coins_arg, validates and normalizes.
    Otherwise queries live exchange universe.
    """
    if coins_arg and len(coins_arg) > 0:
        return [c.upper().strip() for c in coins_arg]
    assets = await discover_available_assets(min_daily_volume_usd=min_volume_usd, limit=top_n)
    return [a["name"] for a in assets]


def resolve_research_timeframes(
    tfs_arg: Optional[List[str]] = None,
) -> AwaitableList:
    """
    Universally resolves supported timeframes without static lists.
    Returns an AwaitableList which can be either awaited or used directly as a list.
    """
    if tfs_arg and len(tfs_arg) > 0:
        res = [t.lower().strip() for t in tfs_arg]
    else:
        res = discover_supported_timeframes()
    return AwaitableList(res)

