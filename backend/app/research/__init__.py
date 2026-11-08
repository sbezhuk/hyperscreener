"""
Universal Research Pipeline Package for Hyperscreener.
Provides dynamic asset and timeframe discovery, isolated caching,
and rigorous data quality validation across all research phases.
"""
from .pipeline import (
    TIMEFRAMES,
    WORKING_TIMEFRAMES,
    TIMEFRAME_STEPS_SECONDS,
    HTF_MAPPING,
    DEFAULT_TIMEFRAME_LIMITS,
    discover_available_assets,
    discover_supported_timeframes,
    get_timeframe_step_seconds,
    get_htf_for_timeframe,
    validate_candle_data_quality,
    get_single_dataset,
    fetch_research_universe,
    resolve_research_coins,
    resolve_research_timeframes,
    MarketDiscoveryError,
    get_cache_dir,
    set_custom_cache_dir,
)

__all__ = [
    "TIMEFRAMES",
    "WORKING_TIMEFRAMES",
    "TIMEFRAME_STEPS_SECONDS",
    "HTF_MAPPING",
    "DEFAULT_TIMEFRAME_LIMITS",
    "discover_available_assets",
    "discover_supported_timeframes",
    "get_timeframe_step_seconds",
    "get_htf_for_timeframe",
    "validate_candle_data_quality",
    "get_single_dataset",
    "fetch_research_universe",
    "resolve_research_coins",
    "resolve_research_timeframes",
    "MarketDiscoveryError",
    "get_cache_dir",
    "set_custom_cache_dir",
]
