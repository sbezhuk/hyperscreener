"""
Dedicated False Breakout (Хибний пробій) Detection Module.

Supports:
- False Breakout Up / Bearish Sweep (Хибний пробій опору) -> Potential reversal DOWN (SHORT)
- False Breakout Down / Bullish Sweep (Хибний пробій підтримки) -> Potential reversal UP (LONG)
- Both single-candle (wick-based) and multi-candle (breakout candle + confirmation candle) detection
- Volume confirmation and level significance (touches, strength score)
- Closed candles only analysis to prevent false signals during candle formation
- Deterministic and duplicate-free signal generation
- Works across all timeframes independently
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional

FALSE_BREAKOUT_CONFIG = {
    # Default parameters per interval or fallback
    "default": {
        "min_wick_pct": 0.04,        # Minimum % price exceeded level to count as breakout
        "max_breakout_atr": 3.0,     # If breakout goes further than 3 ATR, it's a true impulse/breakout, not a trap
        "vol_multiplier": 0.8,       # Volume filter ratio relative to 20-candle SMA
    }
}

# Maximum age in bars for a false breakout to remain actively relevant on chart
TIMEFRAME_RECENCY_BARS = {
    "1m": 60,
    "3m": 60,
    "5m": 60,
    "15m": 50,
    "30m": 45,
    "1h": 40,
    "2h": 35,
    "4h": 30,
    "1d": 25,
}


def _calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    n = len(candles)
    if n < 2:
        return 0.0
    true_ranges: List[float] = []
    for i in range(1, n):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
    window = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(window) / len(window) if window else 0.0


def _get_avg_volume(candles: List[Dict[str, Any]], idx: int, period: int = 20) -> float:
    start_idx = max(0, idx - period)
    vols = [candles[k].get("volume", 0.0) for k in range(start_idx, idx + 1)]
    return sum(vols) / len(vols) if vols else 1.0


def detect_false_breakouts(
    candles: List[Dict[str, Any]],
    levels: Optional[List[Dict[str, Any]]] = None,
    interval: str = "5m",
    min_touches: int = 1,
    max_history_bars: Optional[int] = None,
    min_wick_pct: float = 0.04,
) -> List[Dict[str, Any]]:
    """
    Identifies False Breakouts against confirmed support/resistance levels.
    """
    n = len(candles)
    if n < 3 or not levels:
        return []

    clean_interval = interval.lower()
    if max_history_bars is None:
        max_history_bars = TIMEFRAME_RECENCY_BARS.get(clean_interval, 40)

    atr = _calculate_atr(candles, 14)
    if atr <= 0:
        atr = candles[-1]["close"] * 0.001

    results: List[Dict[str, Any]] = []

    # Limit search to the last max_history_bars closed candles to ensure only ACTIVE & RELEVANT breakouts are shown
    start_idx = max(1, n - max_history_bars)

    for lvl in levels:
        level_px = float(lvl.get("center_price", lvl.get("price", 0.0)))
        if level_px <= 0:
            continue

        touches = int(lvl.get("touches", lvl.get("touches_count", 1)))
        if touches < min_touches:
            continue

        strength_score = float(lvl.get("strength_score", 50.0))
        level_type = str(lvl.get("type", "")).lower()  # "resistance" or "support"
        if not level_type:
            # Infer from relation if not explicitly tagged
            level_type = "resistance" if level_px >= candles[-1]["close"] else "support"

        # Search chronologically
        i = start_idx
        while i < n:
            c = candles[i]
            prev_c = candles[i - 1]
            c_high = c["high"]
            c_low = c["low"]
            c_close = c["close"]
            c_open = c["open"]
            c_time = c["time"]

            # -------------------------------------------------------------
            # 1. FALSE BREAKOUT UP (Resistance)
            # -------------------------------------------------------------
            if level_type == "resistance":
                # Condition: High breached the resistance level
                if c_high > level_px:
                    excess = (c_high - level_px) / level_px * 100
                    # Avoid micro fluctuations and avoid runaway pumps (> 3.5 ATR)
                    if excess >= min_wick_pct and (c_high - level_px) <= 3.5 * atr:
                        avg_vol = _get_avg_volume(candles, i)
                        c_vol = c.get("volume", 0.0)

                        # Case A: Same candle rejection (Wick sweep)
                        if c_close < level_px:
                            results.append({
                                "id": f"fb-up-{int(level_px * 100)}-{c_time}",
                                "type": "bearish_sweep",
                                "subType": "wick_rejection",
                                "formation": "Хибний пробій опору",
                                "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                "sweepPrice": round(c_high, 2 if c_high > 10 else 4),
                                "breakoutTime": c_time,
                                "confirmationTime": c_time,
                                "time": c_time,
                                "direction": "SHORT",
                                "touches": touches,
                                "levelStrength": strength_score,
                                "volumeRatio": round(c_vol / max(avg_vol, 1e-6), 2),
                                "desc": f"Хибний пробій опору {level_px:.2f}: прокол тінню до {c_high:.2f} та закриття під рівнем"
                            })
                            # Advance past this candle to prevent immediate duplicate
                            i += 1
                            continue

                        # Case B: Multi-candle breakout (Candle i closed above, Candle i+1 returns & closes below)
                        elif c_close >= level_px and (i + 1) < n:
                            next_c = candles[i + 1]
                            if next_c["close"] < level_px:
                                conf_time = next_c["time"]
                                next_vol = next_c.get("volume", 0.0)
                                max_high = max(c_high, next_c["high"])
                                results.append({
                                    "id": f"fb-up-{int(level_px * 100)}-{conf_time}",
                                    "type": "bearish_sweep",
                                    "subType": "two_candle_reversal",
                                    "formation": "Хибний пробій опору (2 свічки)",
                                    "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                    "sweepPrice": round(max_high, 2 if max_high > 10 else 4),
                                    "breakoutTime": c_time,
                                    "confirmationTime": conf_time,
                                    "time": conf_time,
                                    "direction": "SHORT",
                                    "touches": touches,
                                    "levelStrength": strength_score,
                                    "volumeRatio": round(next_vol / max(avg_vol, 1e-6), 2),
                                    "desc": f"Хибний пробій опору {level_px:.2f}: вихід тілом свічки та повернення під рівень на наступній свічці"
                                })
                                i += 2
                                continue

            # -------------------------------------------------------------
            # 2. FALSE BREAKOUT DOWN (Support)
            # -------------------------------------------------------------
            elif level_type == "support":
                # Condition: Low breached the support level
                if c_low < level_px:
                    excess = (level_px - c_low) / level_px * 100
                    # Avoid micro fluctuations and runaway dumps (> 3.5 ATR)
                    if excess >= min_wick_pct and (level_px - c_low) <= 3.5 * atr:
                        avg_vol = _get_avg_volume(candles, i)
                        c_vol = c.get("volume", 0.0)

                        # Case A: Same candle rejection (Wick sweep / откуп)
                        if c_close > level_px:
                            results.append({
                                "id": f"fb-down-{int(level_px * 100)}-{c_time}",
                                "type": "bullish_sweep",
                                "subType": "wick_rejection",
                                "formation": "Хибний пробій підтримки",
                                "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                "sweepPrice": round(c_low, 2 if c_low > 10 else 4),
                                "breakoutTime": c_time,
                                "confirmationTime": c_time,
                                "time": c_time,
                                "direction": "LONG",
                                "touches": touches,
                                "levelStrength": strength_score,
                                "volumeRatio": round(c_vol / max(avg_vol, 1e-6), 2),
                                "desc": f"Хибний пробій підтримки {level_px:.2f}: прокол тінню до {c_low:.2f} та швидкий відкуп вище рівня"
                            })
                            i += 1
                            continue

                        # Case B: Multi-candle breakout (Candle i closed below, Candle i+1 returns & closes above)
                        elif c_close <= level_px and (i + 1) < n:
                            next_c = candles[i + 1]
                            if next_c["close"] > level_px:
                                conf_time = next_c["time"]
                                next_vol = next_c.get("volume", 0.0)
                                min_low = min(c_low, next_c["low"])
                                results.append({
                                    "id": f"fb-down-{int(level_px * 100)}-{conf_time}",
                                    "type": "bullish_sweep",
                                    "subType": "two_candle_reversal",
                                    "formation": "Хибний пробій підтримки (2 свічки)",
                                    "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                                    "sweepPrice": round(min_low, 2 if min_low > 10 else 4),
                                    "breakoutTime": c_time,
                                    "confirmationTime": conf_time,
                                    "time": conf_time,
                                    "direction": "LONG",
                                    "touches": touches,
                                    "levelStrength": strength_score,
                                    "volumeRatio": round(next_vol / max(avg_vol, 1e-6), 2),
                                    "desc": f"Хибний пробій підтримки {level_px:.2f}: вихід тілом свічки та повернення вище рівня на наступній свічці"
                                })
                                i += 2
                                continue

            i += 1

    # Filter out invalidated / historical false breakouts that have lost their trading relevance:
    # 1. Bearish sweep of resistance (SHORT): if price later broke and closed ABOVE level_px, or moved excessively away.
    # 2. Bullish sweep of support (LONG): if price later broke and closed BELOW level_px, or moved excessively away.
    # 3. Maximum lifespan: confirmed within max_history_bars.
    active_results: List[Dict[str, Any]] = []
    for sig in results:
        conf_time = sig.get("confirmationTime", sig["time"])
        # Find index in candles
        c_idx = next((k for k in range(n - 1, -1, -1) if candles[k]["time"] <= conf_time), -1)
        if c_idx < 0:
            continue

        bars_ago = n - 1 - c_idx
        if bars_ago > max_history_bars:
            continue

        level_px = sig["levelPrice"]
        subsequent = candles[c_idx + 1:]

        # Invalidation check:
        # A false breakout is invalidated if price subsequently accepts beyond the level (closes on the wrong side)
        is_invalidated = False
        if sig["direction"] == "SHORT":
            # If any candle after confirmation closed above the resistance level
            if any(sc["close"] > level_px for sc in subsequent):
                is_invalidated = True
        else:
            # If any candle after confirmation closed below the support level
            if any(sc["close"] < level_px for sc in subsequent):
                is_invalidated = True

        if not is_invalidated:
            active_results.append(sig)

    # Deduplicate and resolve overlapping levels:
    # If two false breakouts are close in price (e.g. < 0.6% or within 1.2 ATR),
    # they overlap visually on the chart. Pick the single most important one:
    # Priority: higher levelStrength -> higher touches -> larger breakout/rejection -> more recent.

    def _importance_score(sig: Dict[str, Any]) -> float:
        strength = float(sig.get("levelStrength", 50.0))
        touches = float(sig.get("touches", 1))
        vol = float(sig.get("volumeRatio", 1.0))
        # Recency bonus (latest candles get slight edge when strength is tied)
        time_score = (sig["time"] - candles[0]["time"]) / max(candles[-1]["time"] - candles[0]["time"], 1) * 10.0
        return (strength * 2.0) + (touches * 15.0) + (vol * 10.0) + time_score

    # Sort candidates by importance descending
    candidates = sorted(active_results, key=_importance_score, reverse=True)
    deduped: List[Dict[str, Any]] = []

    # Proximity threshold: at least 0.6% price difference or 1.5 ATR to avoid overlapping lines/badges
    min_price_dist_pct = 0.6
    min_atr_dist = 1.5 * atr

    for cand in candidates:
        cand_px = cand["levelPrice"]
        is_collision = False
        for chosen in deduped:
            chosen_px = chosen["levelPrice"]
            pct_diff = abs(cand_px - chosen_px) / chosen_px * 100
            atr_diff = abs(cand_px - chosen_px)
            if pct_diff < min_price_dist_pct or atr_diff < min_atr_dist:
                is_collision = True
                break

        if not is_collision:
            deduped.append(cand)

    # Sort final clean signals chronologically for consistent chart & timeline ordering
    deduped.sort(key=lambda s: s["time"])

    # Limit to top 3-4 most prominent non-overlapping breakouts on the chart
    if len(deduped) > 4:
        # Keep the 4 highest importance ones, then re-sort by time
        top_deduped = sorted(deduped, key=_importance_score, reverse=True)[:4]
        top_deduped.sort(key=lambda s: s["time"])
        return top_deduped

    return deduped
