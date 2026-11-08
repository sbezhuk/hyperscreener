"""
Comprehensive support/resistance zone detection algorithm.

Steps:
 1. Calculate ATR(14)
 2. Find swing highs (resistance) and swing lows (support)
 3. Cluster swings into zones using ATR-based proximity
 4. Count independent touches (all candles, with min_gap)
 5. Measure bounce strength per touch
 6. Calculate composite strength score (0-100)
 7. Detect breakouts
 8. Determine zone status
 9. Apply age-based decay
10. Final filtering (top 5 support + 5 resistance)
11. Add legacy compatibility fields
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

INTERVAL_CONFIG = {
    "1m":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.0, "prominence": 0.5},
    "3m":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.0, "prominence": 0.5},
    "5m":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.0, "prominence": 0.5},
    "15m": {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.0, "prominence": 0.5},
    "30m": {"left": 4, "right": 4, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.2, "prominence": 0.5},
    "1h":  {"left": 4, "right": 4, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.2, "prominence": 0.6},
    "2h":  {"left": 4, "right": 4, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.2, "prominence": 0.6},
    "4h":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.4, "prominence": 0.7},
    "1d":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 2, "min_spacing_atr": 2.5, "prominence": 0.8},
}


# ---------------------------------------------------------------------------
# Step 1 – ATR
# ---------------------------------------------------------------------------

def _calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Return the simple-moving-average ATR for the last `period` candles."""
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

    # Use the last `period` values (or fewer if not enough data)
    window = true_ranges[-period:] if len(true_ranges) >= period else true_ranges
    return sum(window) / len(window) if window else 0.0


# ---------------------------------------------------------------------------
# Step 2 – Swing highs / lows
# ---------------------------------------------------------------------------

def _find_swings(
    candles: List[Dict[str, Any]],
    left_bars: int,
    right_bars: int,
    atr: float = 0.0,
    min_prominence_atr: float = 0.45,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns {"highs": [...], "lows": [...]}.
    Each item: {price, time, index, volume}.
    Uses prominence check to filter out insignificant micro-ripples.
    """
    n = len(candles)
    highs: List[Dict[str, Any]] = []
    lows: List[Dict[str, Any]] = []

    for i in range(left_bars, n - right_bars):
        c = candles[i]
        curr_high = c["high"]
        curr_low = c["low"]

        # Pivot High: strictly greater than all neighbours
        is_high = all(
            candles[i - k]["high"] < curr_high for k in range(1, left_bars + 1)
        ) and all(
            candles[i + k]["high"] < curr_high for k in range(1, right_bars + 1)
        )
        if is_high and atr > 0:
            drop_left = curr_high - min(candles[i - k]["low"] for k in range(1, left_bars + 1))
            drop_right = curr_high - min(candles[i + k]["low"] for k in range(1, right_bars + 1))
            if min(drop_left, drop_right) < min_prominence_atr * atr:
                is_high = False

        # Pivot Low: strictly less than all neighbours
        is_low = all(
            candles[i - k]["low"] > curr_low for k in range(1, left_bars + 1)
        ) and all(
            candles[i + k]["low"] > curr_low for k in range(1, right_bars + 1)
        )
        if is_low and atr > 0:
            rise_left = max(candles[i - k]["high"] for k in range(1, left_bars + 1)) - curr_low
            rise_right = max(candles[i + k]["high"] for k in range(1, right_bars + 1)) - curr_low
            if min(rise_left, rise_right) < min_prominence_atr * atr:
                is_low = False

        if is_high:
            highs.append({"price": curr_high, "time": c["time"], "index": i, "volume": c.get("volume", 0)})
        if is_low:
            lows.append({"price": curr_low, "time": c["time"], "index": i, "volume": c.get("volume", 0)})

    return {"highs": highs, "lows": lows}


# ---------------------------------------------------------------------------
# Step 3 – Cluster swings into zones
# ---------------------------------------------------------------------------

def _cluster_swings(
    swings: List[Dict[str, Any]],
    atr: float,
) -> List[Dict[str, Any]]:
    """
    Merge swings into zones when |price1 - price2| <= 1.0 * ATR.
    Returns list of zone dicts with upper/lower/center price and swing list.
    """
    if not swings or atr <= 0:
        return []

    sorted_swings = sorted(swings, key=lambda x: x["price"])
    merge_threshold = 1.0 * atr

    clusters: List[List[Dict[str, Any]]] = []
    for sw in sorted_swings:
        if not clusters:
            clusters.append([sw])
            continue
        last_cluster = clusters[-1]
        avg_cluster_price = sum(s["price"] for s in last_cluster) / len(last_cluster)
        if abs(sw["price"] - avg_cluster_price) <= merge_threshold:
            last_cluster.append(sw)
        else:
            clusters.append([sw])

    zones: List[Dict[str, Any]] = []
    for cluster in clusters:
        prices = [s["price"] for s in cluster]
        volumes = [max(s["volume"], 1e-9) for s in cluster]
        total_vol = sum(volumes)

        # Volume-weighted center
        center = sum(p * v for p, v in zip(prices, volumes)) / total_vol
        price_min = min(prices)
        price_max = max(prices)

        half_width = max((price_max - price_min) / 2, 0.35 * atr)
        upper_price = center + half_width
        lower_price = center - half_width

        first_time = min(s["time"] for s in cluster)
        last_time = max(s["time"] for s in cluster)
        first_idx = min(s["index"] for s in cluster)
        last_idx = max(s["index"] for s in cluster)

        zones.append({
            "_swings": cluster,
            "center_price": center,
            "upper_price": upper_price,
            "lower_price": lower_price,
            "first_detected_at": first_time,
            "last_tested_at": last_time,
            "_first_idx": first_idx,
            "_last_idx": last_idx,
        })

    return zones


# ---------------------------------------------------------------------------
# Step 4 – Count independent touches
# ---------------------------------------------------------------------------

def _count_touches(
    zone: Dict[str, Any],
    candles: List[Dict[str, Any]],
    zone_type: str,  # "support" | "resistance"
    min_gap: int = 3,
) -> Dict[str, Any]:
    """
    Scan all candles and count independent entries into the zone.
    Returns updated zone with touches_count, touch_volumes, first_detected_at, last_tested_at.
    """
    upper = zone["upper_price"]
    lower = zone["lower_price"]
    n = len(candles)

    touches = 0
    touch_volumes: List[float] = []
    inside = False
    gap_counter = 0
    first_time: int = zone["first_detected_at"]
    last_time: int = zone["last_tested_at"]

    for i, c in enumerate(candles):
        price_field = c["low"] if zone_type == "support" else c["high"]
        in_zone = lower <= price_field <= upper

        if in_zone:
            if not inside and gap_counter >= min_gap:
                touches += 1
                touch_volumes.append(c.get("volume", 0))
                if touches == 1:
                    first_time = c["time"]
                last_time = c["time"]
                inside = True
                gap_counter = 0
            elif not inside and gap_counter < min_gap:
                # too close to last touch – continue counting gap
                pass
        else:
            if inside:
                inside = False
            gap_counter += 1

    zone["touches_count"] = max(touches, 1)
    zone["_touch_volumes"] = touch_volumes
    zone["first_detected_at"] = first_time
    zone["last_tested_at"] = last_time
    return zone


# ---------------------------------------------------------------------------
# Step 5 – Measure bounce strength
# ---------------------------------------------------------------------------

def _measure_bounces(
    zone: Dict[str, Any],
    candles: List[Dict[str, Any]],
    zone_type: str,
    atr: float,
) -> float:
    """
    For each touch, measure how many ATRs price moved in the expected direction.
    Returns average_bounce_atr.
    """
    if atr <= 0:
        return 0.0

    upper = zone["upper_price"]
    lower = zone["lower_price"]
    n = len(candles)
    bounces: List[float] = []
    min_gap = 3

    inside = False
    gap_counter = 0
    exit_idx = -1

    for i, c in enumerate(candles):
        price_field = c["low"] if zone_type == "support" else c["high"]
        in_zone = lower <= price_field <= upper

        if in_zone:
            if not inside and gap_counter >= min_gap:
                inside = True
                gap_counter = 0
                exit_idx = -1
        else:
            if inside:
                inside = False
                exit_idx = i
            gap_counter += 1

            # Measure the bounce starting from exit_idx
            if exit_idx > 0 and not inside:
                look_ahead = min(exit_idx + 20, n)
                if zone_type == "support":
                    # price should go UP
                    best = max((candles[j]["high"] for j in range(exit_idx, look_ahead)), default=candles[exit_idx]["high"])
                    ref = zone["center_price"]
                    bounce_atr = max(best - ref, 0) / atr
                else:
                    # price should go DOWN
                    best = min((candles[j]["low"] for j in range(exit_idx, look_ahead)), default=candles[exit_idx]["low"])
                    ref = zone["center_price"]
                    bounce_atr = max(ref - best, 0) / atr

                if bounce_atr > 0:
                    bounces.append(bounce_atr)
                exit_idx = -1  # reset so we don't double-count

    return sum(bounces) / len(bounces) if bounces else 0.0


# ---------------------------------------------------------------------------
# Step 6 – Strength score
# ---------------------------------------------------------------------------

def _compute_strength_score(
    zone: Dict[str, Any],
    candles: List[Dict[str, Any]],
    zone_type: str,
    average_bounce_atr: float,
    atr: float,
) -> float:
    n = len(candles)
    touches = zone["touches_count"]

    # score_touches: 30% weight, maxes at 5 touches
    score_touches = min(touches / 5, 1.0) * 30

    # score_bounce: 25% weight, maxes at 3 ATR bounce
    score_bounce = min(average_bounce_atr / 3, 1.0) * 25

    # volume_confirmation: ratio of touch volumes above average candle volume
    avg_vol = sum(c.get("volume", 0) for c in candles) / max(n, 1)
    touch_vols = zone.get("_touch_volumes", [])
    if touch_vols:
        above_avg = sum(1 for v in touch_vols if v >= avg_vol)
        volume_confirmation = above_avg / len(touch_vols)
    else:
        volume_confirmation = 0.0
    score_volume = volume_confirmation * 15

    # recency_score: linear decay based on distance from last tested candle
    first_idx = zone.get("_first_idx", 0)
    # Find the index of the last tested candle
    last_time = zone["last_tested_at"]
    last_idx = next((i for i, c in reversed(list(enumerate(candles))) if c["time"] <= last_time), 0)
    candles_since = n - 1 - last_idx
    recency_window = int(0.2 * n)
    if candles_since <= recency_window:
        recency_score = 1.0
    else:
        decay = (candles_since - recency_window) / max(n - recency_window, 1)
        recency_score = max(1.0 - decay, 0.0)
    score_recency = recency_score * 15

    # closes_beyond_zone: ratio of candles after first touch that closed beyond zone
    # Support: closed ABOVE upper (price moved up = confirms support)
    # Resistance: closed BELOW lower (price moved down = confirms resistance)
    check_start = first_idx
    check_end = min(check_start + 50, n)
    if check_end > check_start:
        if zone_type == "support":
            beyond = sum(1 for c in candles[check_start:check_end] if c["close"] > zone["upper_price"])
        else:
            beyond = sum(1 for c in candles[check_start:check_end] if c["close"] < zone["lower_price"])
        closes_beyond = beyond / (check_end - check_start)
    else:
        closes_beyond = 0.0
    score_closes = closes_beyond * 15

    raw = score_touches + score_bounce + score_volume + score_recency + score_closes

    # Age-based decay: zones last tested more than 50% of total candles ago → 20% penalty
    if candles_since > 0.5 * n:
        raw *= 0.80

    return min(round(raw, 2), 100.0)


# ---------------------------------------------------------------------------
# Legacy compatibility fields
# ---------------------------------------------------------------------------

def _add_legacy_fields(zone: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    center = zone["center_price"]
    decimals = 6 if center < 1 else 4 if center < 100 else 2

    dist_pct = (center - current_price) / current_price * 100 if current_price > 0 else 0.0

    zone["price"] = round(center, decimals)
    zone["top"] = round(zone["upper_price"], decimals)
    zone["bottom"] = round(zone["lower_price"], decimals)
    zone["touches"] = zone["touches_count"]
    zone["firstTime"] = zone.get("first_detected_at", 0)
    zone["latestTime"] = zone.get("last_tested_at", 0)
    zone["distPct"] = round(dist_pct, 2)
    zone["strength"] = int(min(zone.get("strength_score", 0) / 20, 5))
    return zone


# ---------------------------------------------------------------------------
# Pivot Points Engine (Classic Floor Pivots)
# ---------------------------------------------------------------------------

def extract_previous_period_ohlc(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    period_type: str = "auto",
) -> Optional[Dict[str, Any]]:
    """
    Extracts the High, Low, Close, and Open of the previous completed trading period
    (Daily or Weekly) from a list of candles.
    """
    if not candles:
        return None

    clean_interval = interval.lower()
    if period_type == "auto":
        period_type = "weekly" if clean_interval in ("1d", "3d", "1w") else "daily"

    def _get_ts(c: Dict[str, Any]) -> int:
        t = c.get("time", 0)
        return int(t / 1000) if t > 1e11 else int(t)

    # Group candles by period
    periods: Dict[str, List[Dict[str, Any]]] = {}
    for c in candles:
        ts = _get_ts(c)
        if ts <= 0:
            continue
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if period_type == "weekly":
                iso_year, iso_week, _ = dt.isocalendar()
                key = f"{iso_year}-W{iso_week:02d}"
            else:
                key = dt.strftime("%Y-%m-%d")
        except Exception:
            key = "session_0"

        if key not in periods:
            periods[key] = []
        periods[key].append(c)

    sorted_keys = sorted(periods.keys())

    # If we have at least 2 distinct calendar periods:
    # the last key is current (incomplete/ongoing), the second to last is previous completed period!
    if len(sorted_keys) >= 2:
        prev_key = sorted_keys[-2]
        prev_candles = periods[prev_key]
        high = max(c["high"] for c in prev_candles)
        low = min(c["low"] for c in prev_candles)
        close = prev_candles[-1]["close"]
        open_px = prev_candles[0]["open"]
        first_time = _get_ts(prev_candles[0])
        last_time = _get_ts(prev_candles[-1])
        return {
            "period": period_type,
            "period_key": prev_key,
            "high": high,
            "low": low,
            "close": close,
            "open": open_px,
            "first_time": first_time,
            "last_time": last_time,
            "candle_count": len(prev_candles),
        }

    # If interval is 1d and len >= 2, the previous candle is yesterday!
    if clean_interval == "1d" and len(candles) >= 2:
        prev_c = candles[-2]
        return {
            "period": "daily",
            "period_key": "previous_1d_bar",
            "high": prev_c["high"],
            "low": prev_c["low"],
            "close": prev_c["close"],
            "open": prev_c["open"],
            "first_time": _get_ts(prev_c),
            "last_time": _get_ts(prev_c),
            "candle_count": 1,
        }

    # If all candles fall into 1 calendar day/session (or synthetic test candles):
    if len(candles) >= 4:
        split_idx = max(len(candles) // 2, 1)
        prev_candles = candles[:split_idx]
        high = max(c["high"] for c in prev_candles)
        low = min(c["low"] for c in prev_candles)
        close = prev_candles[-1]["close"]
        open_px = prev_candles[0]["open"]
        return {
            "period": period_type,
            "period_key": "previous_session",
            "high": high,
            "low": low,
            "close": close,
            "open": open_px,
            "first_time": _get_ts(prev_candles[0]),
            "last_time": _get_ts(prev_candles[-1]),
            "candle_count": len(prev_candles),
        }

    # Minimal fallback
    c0 = candles[0]
    return {
        "period": period_type,
        "period_key": "initial_candle",
        "high": c0["high"],
        "low": c0["low"],
        "close": c0["close"],
        "open": c0["open"],
        "first_time": _get_ts(c0),
        "last_time": _get_ts(c0),
        "candle_count": 1,
    }


def calculate_pivot_points(
    candles: Optional[List[Dict[str, Any]]] = None,
    high: Optional[float] = None,
    low: Optional[float] = None,
    close: Optional[float] = None,
    interval: str = "5m",
    period_type: str = "auto",
) -> Dict[str, Any]:
    """
    Calculates Classic Floor Pivot Points (PP, R1, R2, R3, S1, S2, S3)
    based on the previous trading period (Day or Week) with High, Low, Close.

    Formulas:
      • Базовий рівень (Pivot Point, PP):
        PP = (High + Low + Close) / 3
      • Рівні опору (Resistance):
        R1 = (2 * PP) - Low
        R2 = PP + (High - Low)
        R3 = High + 2 * (PP - Low)
      • Рівні підтримки (Support):
        S1 = (2 * PP) - High
        S2 = PP - (High - Low)
        S3 = Low - 2 * (High - PP)
    """
    period_key = ""
    first_time = 0
    last_time = 0

    if high is None or low is None or close is None:
        if not candles:
            return {}
        extracted = extract_previous_period_ohlc(candles, interval=interval, period_type=period_type)
        if not extracted:
            return {}
        high = extracted["high"]
        low = extracted["low"]
        close = extracted["close"]
        period = extracted["period"]
        period_key = extracted.get("period_key", "")
        first_time = extracted.get("first_time", 0)
        last_time = extracted.get("last_time", 0)
    else:
        period = period_type if period_type != "auto" else "daily"
        period_key = "custom"
        if candles:
            first_time = candles[0].get("time", 0)
            last_time = candles[-1].get("time", 0)

    if high < low:
        high, low = low, high

    # Classic Floor Pivot Point Formulas as requested
    pp = (high + low + close) / 3.0
    r1 = (2.0 * pp) - low
    r2 = pp + (high - low)
    r3 = high + 2.0 * (pp - low)
    s1 = (2.0 * pp) - high
    s2 = pp - (high - low)
    s3 = low - 2.0 * (high - pp)

    decimals = 6 if pp < 1 else 4 if pp < 100 else 2

    return {
        "period": period,
        "period_key": period_key,
        "first_time": first_time,
        "last_time": last_time,
        "high": round(high, decimals),
        "low": round(low, decimals),
        "close": round(close, decimals),
        "pp": round(pp, decimals),
        "r1": round(r1, decimals),
        "r2": round(r2, decimals),
        "r3": round(r3, decimals),
        "s1": round(s1, decimals),
        "s2": round(s2, decimals),
        "s3": round(s3, decimals),
    }


# ---------------------------------------------------------------------------
# Smart Money Concepts (SMC) Engine: Order Blocks, Breakers & Liquidity Pools
# ---------------------------------------------------------------------------

def _detect_smc_order_blocks(
    candles: List[Dict[str, Any]],
    atr: float,
    current_price: float,
    interval: str = "5m",
) -> List[Dict[str, Any]]:
    """
    Detects institutional Smart Money Order Blocks (OB) and Breaker Blocks.
    - Bullish OB (Demand): The last bearish candle before an aggressive upward displacement
      that breaks structure or creates an imbalance (FVG).
    - Bearish OB (Supply): The last bullish candle before an aggressive downward displacement
      that breaks structure or creates an imbalance (FVG).
    - Breaker Blocks: An Order Block whose boundary was violated with a candle close,
      flipping its role (Role Reversal).
    """
    n = len(candles)
    if n < 4 or atr <= 0:
        return []

    order_blocks: List[Dict[str, Any]] = []
    decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2

    # Focus scan on recent structural context (last 75 candles)
    # Ancient broken candles from hundreds of bars ago are historical noise, not active trading zones.
    lookback = min(n - 2, 75)
    start_idx = max(0, n - 2 - lookback)

    for i in range(start_idx, n - 2):
        c = candles[i]
        c_open = c["open"]
        c_close = c["close"]
        c_high = c["high"]
        c_low = c["low"]
        c_time = c.get("time", 0)

        # 1. Bullish Order Block (Demand candidate):
        is_bearish = c_close <= c_open or (c_close - c_low) < (c_high - c_close)
        if is_bearish:
            future_candles = candles[i + 1 : min(i + 4, n)]
            if future_candles:
                max_future_high = max(fc["high"] for fc in future_candles)
                max_future_close = max(fc["close"] for fc in future_candles)
                displacement = max_future_high - c_low

                # Criteria: closes above candle high and displacement >= 1.0 * ATR
                if (max_future_close > c_high and displacement >= 1.0 * atr) or (displacement >= 1.4 * atr):
                    has_fvg = bool(i + 2 < n and candles[i + 2]["low"] > c_high)
                    prior_highs = [candles[k]["high"] for k in range(max(0, i - 12), i)]
                    caused_bos = bool(prior_highs and max_future_high > max(prior_highs))

                    ob_top = c_high
                    ob_bottom = c_low
                    ob_center = (ob_top + ob_bottom) / 2.0

                    subsequent = candles[i + len(future_candles) : n]
                    is_broken = False
                    break_idx = -1
                    touches = 1
                    latest_tested = c_time

                    for s_idx, sc in enumerate(subsequent):
                        if sc["close"] < ob_bottom:
                            is_broken = True
                            break_idx = i + len(future_candles) + s_idx
                            latest_tested = sc.get("time", latest_tested)
                            break
                        elif sc["low"] <= ob_top and sc["high"] >= ob_bottom:
                            touches += 1
                            latest_tested = sc.get("time", latest_tested)

                    if not is_broken:
                        # Clean active or mitigated Demand OB
                        # Only valid as support when current price is strictly ABOVE the demand zone
                        if current_price >= ob_top:
                            is_mitigated = touches > 1
                            status = "retested" if is_mitigated else "active"
                            base_score = 82.0 if is_mitigated else 92.0
                            if has_fvg:
                                base_score += 5.0
                            if caused_bos:
                                base_score += 4.0

                            order_blocks.append({
                                "center_price": round(ob_center, decimals),
                                "upper_price": round(ob_top, decimals),
                                "lower_price": round(ob_bottom, decimals),
                                "touches_count": min(touches, 3),
                                "average_bounce_atr": 1.5,
                                "volume_confirmation": 0.85,
                                "strength_score": min(base_score, 100.0),
                                "status": status,
                                "zone_id": f"smc-ob-dem-{i}-{str(uuid.uuid4())[:4]}",
                                "type": "support",
                                "timeframe": interval,
                                "first_detected_at": c_time,
                                "last_tested_at": latest_tested,
                                "smc_type": "ORDER_BLOCK",
                                "smc_label": "OB Demand",
                                "is_mitigated": is_mitigated,
                                "has_fvg": has_fvg,
                                "caused_bos": caused_bos,
                            })
                    else:
                        # Breaker Block validation:
                        # A broken Bullish OB only becomes a valid Bearish Breaker (Resistance) if:
                        # 1. The break is relatively recent (within 40 bars)
                        # 2. Current price is strictly below the zone (overhead resistance)
                        # 3. Price hasn't closed back above ob_top (not invalidated chop)
                        bars_since_break = n - break_idx if break_idx >= 0 else 999
                        after_break = candles[break_idx + 1 : n] if break_idx >= 0 else []
                        closed_back_above = any(ac["close"] > ob_top for ac in after_break)

                        if (
                            bars_since_break <= 40
                            and current_price <= ob_bottom
                            and not closed_back_above
                        ):
                            order_blocks.append({
                                "center_price": round(ob_center, decimals),
                                "upper_price": round(ob_top, decimals),
                                "lower_price": round(ob_bottom, decimals),
                                "touches_count": min(touches, 3),
                                "average_bounce_atr": 1.3,
                                "volume_confirmation": 0.80,
                                "strength_score": 78.0,
                                "status": "retested",
                                "zone_id": f"smc-brk-res-{i}-{str(uuid.uuid4())[:4]}",
                                "type": "resistance",
                                "timeframe": interval,
                                "first_detected_at": c_time,
                                "last_tested_at": latest_tested,
                                "smc_type": "BREAKER_BLOCK",
                                "smc_label": "Breaker",
                                "is_mitigated": True,
                                "has_fvg": has_fvg,
                                "caused_bos": caused_bos,
                            })

        # 2. Bearish Order Block (Supply candidate):
        is_bullish = c_close >= c_open or (c_high - c_close) < (c_close - c_low)
        if is_bullish:
            future_candles = candles[i + 1 : min(i + 4, n)]
            if future_candles:
                min_future_low = min(fc["low"] for fc in future_candles)
                min_future_close = min(fc["close"] for fc in future_candles)
                displacement = c_high - min_future_low

                # Criteria: closes below candle low and displacement >= 1.0 * ATR
                if (min_future_close < c_low and displacement >= 1.0 * atr) or (displacement >= 1.4 * atr):
                    has_fvg = bool(i + 2 < n and candles[i + 2]["high"] < c_low)
                    prior_lows = [candles[k]["low"] for k in range(max(0, i - 12), i)]
                    caused_bos = bool(prior_lows and min_future_low < min(prior_lows))

                    ob_top = c_high
                    ob_bottom = c_low
                    ob_center = (ob_top + ob_bottom) / 2.0

                    subsequent = candles[i + len(future_candles) : n]
                    is_broken = False
                    break_idx = -1
                    touches = 1
                    latest_tested = c_time

                    for s_idx, sc in enumerate(subsequent):
                        if sc["close"] > ob_top:
                            is_broken = True
                            break_idx = i + len(future_candles) + s_idx
                            latest_tested = sc.get("time", latest_tested)
                            break
                        elif sc["high"] >= ob_bottom and sc["low"] <= ob_top:
                            touches += 1
                            latest_tested = sc.get("time", latest_tested)

                    if not is_broken:
                        # Clean active or mitigated Supply OB
                        # Only valid as resistance when current price is strictly BELOW the supply zone
                        if current_price <= ob_bottom:
                            is_mitigated = touches > 1
                            status = "retested" if is_mitigated else "active"
                            base_score = 82.0 if is_mitigated else 92.0
                            if has_fvg:
                                base_score += 5.0
                            if caused_bos:
                                base_score += 4.0

                            order_blocks.append({
                                "center_price": round(ob_center, decimals),
                                "upper_price": round(ob_top, decimals),
                                "lower_price": round(ob_bottom, decimals),
                                "touches_count": min(touches, 3),
                                "average_bounce_atr": 1.5,
                                "volume_confirmation": 0.85,
                                "strength_score": min(base_score, 100.0),
                                "status": status,
                                "zone_id": f"smc-ob-sup-{i}-{str(uuid.uuid4())[:4]}",
                                "type": "resistance",
                                "timeframe": interval,
                                "first_detected_at": c_time,
                                "last_tested_at": latest_tested,
                                "smc_type": "ORDER_BLOCK",
                                "smc_label": "OB Supply",
                                "is_mitigated": is_mitigated,
                                "has_fvg": has_fvg,
                                "caused_bos": caused_bos,
                            })
                    else:
                        # Breaker Block validation:
                        # A broken Bearish OB only becomes a valid Bullish Breaker (Support) if:
                        # 1. The break is relatively recent (within 40 bars)
                        # 2. Current price is strictly above the zone (underlying support)
                        # 3. Price hasn't closed back below ob_bottom
                        bars_since_break = n - break_idx if break_idx >= 0 else 999
                        after_break = candles[break_idx + 1 : n] if break_idx >= 0 else []
                        closed_back_below = any(ac["close"] < ob_bottom for ac in after_break)

                        if (
                            bars_since_break <= 40
                            and current_price >= ob_top
                            and not closed_back_below
                        ):
                            order_blocks.append({
                                "center_price": round(ob_center, decimals),
                                "upper_price": round(ob_top, decimals),
                                "lower_price": round(ob_bottom, decimals),
                                "touches_count": min(touches, 3),
                                "average_bounce_atr": 1.3,
                                "volume_confirmation": 0.80,
                                "strength_score": 78.0,
                                "status": "retested",
                                "zone_id": f"smc-brk-sup-{i}-{str(uuid.uuid4())[:4]}",
                                "type": "support",
                                "timeframe": interval,
                                "first_detected_at": c_time,
                                "last_tested_at": latest_tested,
                                "smc_type": "BREAKER_BLOCK",
                                "smc_label": "Breaker",
                                "is_mitigated": True,
                                "has_fvg": has_fvg,
                                "caused_bos": caused_bos,
                            })

    return order_blocks


def _detect_smc_liquidity_pools(
    candles: List[Dict[str, Any]],
    swings: Dict[str, List[Dict[str, Any]]],
    atr: float,
    current_price: float,
    interval: str = "5m",
) -> List[Dict[str, Any]]:
    """
    Detects Buy-Side Liquidity (BSL / Equal Highs) and Sell-Side Liquidity (SSL / Equal Lows).
    Smart money targets these zones to engineer liquidity against retail stop-losses.
    """
    if atr <= 0 or not candles:
        return []

    pools: List[Dict[str, Any]] = []
    decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2
    tolerance = 0.4 * atr

    # 1. BSL - Equal Highs (EQH)
    highs = swings.get("highs", [])
    if len(highs) >= 2:
        used = set()
        for i in range(len(highs)):
            if i in used:
                continue
            cluster = [highs[i]]
            for j in range(i + 1, len(highs)):
                if j in used:
                    continue
                if abs(highs[j]["price"] - highs[i]["price"]) <= tolerance:
                    cluster.append(highs[j])
                    used.add(j)
            if len(cluster) >= 2:
                used.add(i)
                avg_px = sum(h["price"] for h in cluster) / len(cluster)
                max_px = max(h["price"] for h in cluster)
                min_time = min(h["time"] for h in cluster)
                max_time = max(h["time"] for h in cluster)
                top = max_px + 0.15 * atr
                bottom = avg_px - 0.25 * atr

                is_swept = any(c["high"] > top for c in candles if c["time"] > max_time)
                # If swept and price has drifted far away, pool liquidity is exhausted
                if is_swept and abs(avg_px - current_price) > 3.0 * atr:
                    continue

                # BSL (Buy-side Liquidity) acts as overhead resistance above current price
                if avg_px <= current_price:
                    continue
                bottom = max(avg_px - 0.25 * atr, current_price + 0.05 * atr)
                zone_type = "resistance"
                score = 75.0 if is_swept else min(88.0 + len(cluster) * 3.0, 98.0)

                pools.append({
                    "center_price": round(avg_px, decimals),
                    "upper_price": round(top, decimals),
                    "lower_price": round(bottom, decimals),
                    "touches_count": min(len(cluster), 3),
                    "average_bounce_atr": 1.3,
                    "volume_confirmation": 0.75,
                    "strength_score": score,
                    "status": "retested" if is_swept else "active",
                    "zone_id": f"smc-bsl-{str(uuid.uuid4())[:4]}",
                    "type": zone_type,
                    "timeframe": interval,
                    "first_detected_at": min_time,
                    "last_tested_at": max_time,
                    "smc_type": "LIQUIDITY_POOL",
                    "smc_label": "BSL",
                    "is_mitigated": is_swept,
                })

    # 2. SSL - Equal Lows (EQL)
    lows = swings.get("lows", [])
    if len(lows) >= 2:
        used = set()
        for i in range(len(lows)):
            if i in used:
                continue
            cluster = [lows[i]]
            for j in range(i + 1, len(lows)):
                if j in used:
                    continue
                if abs(lows[j]["price"] - lows[i]["price"]) <= tolerance:
                    cluster.append(lows[j])
                    used.add(j)
            if len(cluster) >= 2:
                used.add(i)
                avg_px = sum(l["price"] for l in cluster) / len(cluster)
                min_px = min(l["price"] for l in cluster)
                min_time = min(l["time"] for l in cluster)
                max_time = max(l["time"] for l in cluster)
                top = avg_px + 0.25 * atr
                bottom = min_px - 0.15 * atr

                is_swept = any(c["low"] < bottom for c in candles if c["time"] > max_time)
                # If swept and price drifted far away, pool is exhausted
                if is_swept and abs(avg_px - current_price) > 3.0 * atr:
                    continue

                # SSL (Sell-side Liquidity) acts as underlying support below current price
                if avg_px >= current_price:
                    continue
                top = min(avg_px + 0.25 * atr, current_price - 0.05 * atr)
                zone_type = "support"
                score = 75.0 if is_swept else min(88.0 + len(cluster) * 3.0, 98.0)

                pools.append({
                    "center_price": round(avg_px, decimals),
                    "upper_price": round(top, decimals),
                    "lower_price": round(bottom, decimals),
                    "touches_count": min(len(cluster), 3),
                    "average_bounce_atr": 1.3,
                    "volume_confirmation": 0.75,
                    "strength_score": score,
                    "status": "retested" if is_swept else "active",
                    "zone_id": f"smc-ssl-{str(uuid.uuid4())[:4]}",
                    "type": zone_type,
                    "timeframe": interval,
                    "first_detected_at": min_time,
                    "last_tested_at": max_time,
                    "smc_type": "LIQUIDITY_POOL",
                    "smc_label": "SSL",
                    "is_mitigated": is_swept,
                })

    return pools


# ---------------------------------------------------------------------------
# Public API: analyze_levels (Smart Money Concepts Architecture)
# ---------------------------------------------------------------------------

def analyze_levels(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    period_type: str = "auto",
    prev_high: Optional[float] = None,
    prev_low: Optional[float] = None,
    prev_close: Optional[float] = None,
    include_pivots: bool = False,
) -> Dict[str, Any]:
    """
    Analyzes candlestick data and returns confirmed Smart Money Concepts (SMC)
    support/resistance zones:
    - Institutional Order Blocks (OB Demand & OB Supply)
    - Breaker Blocks (Role Reversal Mitigation Levels)
    - Buy-Side & Sell-Side Liquidity Pools (BSL / SSL / EQH / EQL)
    - Major Structural Swing Boundaries
    """
    if not candles:
        return {"currentPrice": 0.0, "resistances": [], "supports": [], "cascades": [], "pivot_points": {}}

    clean_interval = interval.lower()
    cfg = INTERVAL_CONFIG.get(clean_interval, INTERVAL_CONFIG["5m"])

    left_bars: int = cfg["left"]
    right_bars: int = cfg["right"]
    atr_period: int = cfg["atr_period"]
    max_zones: int = cfg["max_zones"]

    current_price: float = candles[-1]["close"]
    n = len(candles)
    decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2

    # Step 1 – ATR
    atr = _calculate_atr(candles, atr_period)
    if atr <= 0:
        atr = current_price * 0.001

    # Keep classic pivot calculations available for full backward compatibility
    pivots = calculate_pivot_points(
        candles=candles,
        high=prev_high,
        low=prev_low,
        close=prev_close,
        interval=clean_interval,
        period_type=period_type,
    )

    # Step 2 – Swing detection
    prominence = cfg.get("prominence", 0.5)
    swings = _find_swings(candles, left_bars, right_bars, atr=atr, min_prominence_atr=prominence)

    # Step 3 – Smart Money Concepts Detection:
    # 3.1 Order Blocks & Breakers
    smc_obs = _detect_smc_order_blocks(candles, atr, current_price, interval=interval)

    # 3.2 Liquidity Pools (BSL / SSL)
    smc_pools = _detect_smc_liquidity_pools(candles, swings, atr, current_price, interval=interval)

    # 3.3 Key Structural Swings (Swing Demand & Supply)
    structural_swings: List[Dict[str, Any]] = []
    for h in swings.get("highs", []):
        px = h["price"]
        if px > current_price:
            half_w = max(0.20 * atr, px * 0.0008)
            lower_p = max(px - half_w, current_price + 0.05 * atr)
            structural_swings.append({
                "center_price": round(px, decimals),
                "upper_price": round(px + half_w, decimals),
                "lower_price": round(lower_p, decimals),
                "touches_count": 1,
                "average_bounce_atr": 1.2,
                "volume_confirmation": 0.7,
                "strength_score": 75.0,
                "status": "active",
                "zone_id": f"smc-struct-h-{str(uuid.uuid4())[:4]}",
                "type": "resistance",
                "timeframe": interval,
                "first_detected_at": h["time"],
                "last_tested_at": h["time"],
                "smc_type": "STRUCTURE_ORIGIN",
                "smc_label": "Supply",
            })

    for l in swings.get("lows", []):
        px = l["price"]
        if px < current_price:
            half_w = max(0.20 * atr, px * 0.0008)
            upper_p = min(px + half_w, current_price - 0.05 * atr)
            structural_swings.append({
                "center_price": round(px, decimals),
                "upper_price": round(upper_p, decimals),
                "lower_price": round(px - half_w, decimals),
                "touches_count": 1,
                "average_bounce_atr": 1.2,
                "volume_confirmation": 0.7,
                "strength_score": 75.0,
                "status": "active",
                "zone_id": f"smc-struct-l-{str(uuid.uuid4())[:4]}",
                "type": "support",
                "timeframe": interval,
                "first_detected_at": l["time"],
                "last_tested_at": l["time"],
                "smc_type": "STRUCTURE_ORIGIN",
                "smc_label": "Demand",
            })

    # Optional classic pivot points candidate generation if explicitly requested
    pivot_candidates: List[Dict[str, Any]] = []
    if include_pivots and pivots:
        pivot_items = [
            ("R3", pivots.get("r3")),
            ("R2", pivots.get("r2")),
            ("R1", pivots.get("r1")),
            ("PP", pivots.get("pp")),
            ("S1", pivots.get("s1")),
            ("S2", pivots.get("s2")),
            ("S3", pivots.get("s3")),
        ]
        p_first = pivots.get("first_time") or (candles[0].get("time", 0) if candles else 0)
        p_last = pivots.get("last_time") or (candles[-1].get("time", 0) if candles else 0)
        for label, px in pivot_items:
            if px is None or px <= 0:
                continue
            zone_type = "resistance" if px >= current_price else "support"
            status = "retested" if (label.startswith("R") and px < current_price) or (label.startswith("S") and px > current_price) else "active"
            half_w = max(0.25 * atr, px * 0.0008)
            pivot_candidates.append({
                "center_price": round(px, decimals),
                "upper_price": round(px + half_w, decimals),
                "lower_price": round(px - half_w, decimals),
                "touches_count": 1,
                "average_bounce_atr": 1.2,
                "volume_confirmation": 0.7,
                "strength_score": 80.0,
                "status": status,
                "zone_id": f"pivot-{label.lower()}-{str(uuid.uuid4())[:4]}",
                "type": zone_type,
                "timeframe": interval,
                "first_detected_at": p_first,
                "last_tested_at": p_last,
                "is_pivot": True,
                "pivot_label": label,
            })

    # Combine all SMC candidates: Order Blocks take highest priority, then Liquidity Pools, then Swings
    all_candidates = smc_obs + smc_pools + structural_swings + pivot_candidates

    # Format with legacy fields
    formatted_candidates: List[Dict[str, Any]] = []
    for c in all_candidates:
        formatted_candidates.append(_add_legacy_fields(c, current_price))

    # Separate into resistances (above current price) and supports (below current price)
    # Strict SMC Dealing Range Separation:
    # A resistance MUST reside strictly ABOVE current price (bottom >= current_price)
    # A support MUST reside strictly BELOW current price (top <= current_price)
    resistances_pool = [
        c for c in formatted_candidates
        if c["type"] == "resistance" and c["bottom"] >= current_price and c["price"] > current_price
    ]
    supports_pool = [
        c for c in formatted_candidates
        if c["type"] == "support" and c["top"] <= current_price and c["price"] < current_price
    ]

    # Spacing and Confluence Selection:
    # Generous minimum separation between key levels to eliminate chart noise and band stacking
    if include_pivots:
        min_sep = 0.4 * atr
        max_key_zones = 5
    else:
        min_sep = max(cfg.get("min_spacing_atr", 2.2) * atr, current_price * 0.015)
        max_key_zones = min(cfg.get("max_zones", 2), 2)

    def _select_smc_zones(z_list: List[Dict[str, Any]], is_resistance: bool) -> List[Dict[str, Any]]:
        if not z_list:
            return []

        # Calculate composite institutional ranking for each candidate:
        # Prioritize:
        # 1. SMC Institutional Tier: Unmitigated OB > Unswept Liquidity Pool > Breaker > Mitigated OB > Swing
        # 2. Proximity: levels closer to current price are more immediately relevant
        for z in z_list:
            smc_t = z.get("smc_type", "")
            is_mit = z.get("is_mitigated", False)
            type_bonus = 0.0
            if smc_t == "ORDER_BLOCK":
                type_bonus = 28.0 if not is_mit else 16.0
            elif smc_t == "LIQUIDITY_POOL":
                type_bonus = 22.0 if not is_mit else 12.0
            elif smc_t == "BREAKER_BLOCK":
                type_bonus = 14.0
            else:
                type_bonus = 6.0

            dist_atr = abs(z["center_price"] - current_price) / max(atr, 1e-6)
            # Gentle proximity penalty so distant noise is deprioritized
            dist_penalty = min(dist_atr * 1.2, 20.0)

            z["_composite_score"] = z.get("strength_score", 70.0) + type_bonus - dist_penalty

        selected: List[Dict[str, Any]] = []

        # Step 1: Select Level 1 (Nearest Reaction Barrier)
        # Search for the best candidate within immediate range (0.2 to 4.5 ATR of current price)
        near_candidates = [z for z in z_list if abs(z["center_price"] - current_price) <= 4.5 * atr]
        if near_candidates:
            near_candidates.sort(key=lambda z: z["_composite_score"], reverse=True)
            selected.append(near_candidates[0])
        else:
            # Fallback: take the candidate closest to price
            z_list.sort(key=lambda z: abs(z["center_price"] - current_price))
            selected.append(z_list[0])

        # Step 2: Select Level 2 (Major Target / Liquidity Boundary)
        # Must be separated from already selected levels by at least min_sep
        remaining = [
            z for z in z_list
            if all(abs(z["center_price"] - sz["center_price"]) >= min_sep for sz in selected)
        ]

        while remaining and len(selected) < max_key_zones:
            # Prioritize major structural boundary, liquidity pool, or high-tier SMC setup
            remaining.sort(key=lambda z: z["_composite_score"], reverse=True)
            chosen = remaining.pop(0)
            selected.append(chosen)
            remaining = [
                z for z in remaining
                if abs(z["center_price"] - chosen["center_price"]) >= min_sep
            ]

        # Confluence merging: for any candidates close to selected levels (within min_sep),
        # merge their institutional confluence into the selected level without stacking
        for z in z_list:
            if z in selected:
                continue
            confluent = next((sz for sz in selected if abs(z["center_price"] - sz["center_price"]) < min_sep), None)
            if confluent:
                confluent["touches"] = min(max(confluent.get("touches", 1), z.get("touches", 1)), 3)
                confluent["strength_score"] = min(confluent.get("strength_score", 75.0) + 3.0, 100.0)
                # Upgrade label if confluent candidate has higher institutional tier
                if z.get("smc_type") == "ORDER_BLOCK" and confluent.get("smc_type") != "ORDER_BLOCK":
                    confluent["smc_type"] = z["smc_type"]
                    confluent["smc_label"] = "OB Supply" if is_resistance else "OB Demand"
                elif z.get("smc_type") == "LIQUIDITY_POOL" and confluent.get("smc_type") not in ("ORDER_BLOCK", "LIQUIDITY_POOL"):
                    confluent["smc_type"] = z["smc_type"]
                    confluent["smc_label"] = "BSL" if is_resistance else "SSL"

        # Clean up temporary composite score field and enforce strict polarity rules:
        # A resistance can NEVER carry Demand label; a support can NEVER carry Supply label.
        for z in selected:
            z.pop("_composite_score", None)
            if is_resistance:
                z["type"] = "resistance"
                if z.get("smc_label") in ("OB Demand", "Demand"):
                    z["smc_label"] = "OB Supply"
            else:
                z["type"] = "support"
                if z.get("smc_label") in ("OB Supply", "Supply"):
                    z["smc_label"] = "OB Demand"

        return selected

    clean_resistances = _select_smc_zones(resistances_pool, is_resistance=True)
    clean_supports = _select_smc_zones(supports_pool, is_resistance=False)

    # Sort resistances ascending (closest above price first)
    clean_resistances.sort(key=lambda r: r["price"])
    # Sort supports descending (closest below price first)
    clean_supports.sort(key=lambda s: s["price"], reverse=True)

    # Cross-Polarity Non-Collision Invariant:
    # Under NO circumstances can a resistance and a support occupy the same level or overlap!
    min_dealing_gap = max(0.8 * atr, current_price * 0.006)
    while clean_resistances and clean_supports and (clean_resistances[0]["bottom"] < clean_supports[0]["top"] + min_dealing_gap):
        # A collision occurred: resistance bottom is too close to or below support top!
        # Eliminate the inner candidate that is local chop closer to current price
        dist_r = abs(clean_resistances[0]["price"] - current_price)
        dist_s = abs(clean_supports[0]["price"] - current_price)
        if dist_r <= dist_s:
            clean_resistances.pop(0)
        else:
            clean_supports.pop(0)

    # Dynamic Discovery: if no supports or resistances exist (e.g. price at ATH, ATL, or after collision pruning)
    if not clean_supports:
        candidate_lows = [s for s in swings.get("lows", []) if s["price"] < current_price - 0.2 * atr]
        if candidate_lows:
            candidate_lows.sort(key=lambda s: s["time"], reverse=True)
            chosen_l = candidate_lows[0]["price"]
            s_time = candidate_lows[0].get("time", candles[-1]["time"] if candles else 0)
        else:
            recent_lows = [c["low"] for c in candles[-min(len(candles), 50):] if c["low"] < current_price - 0.2 * atr]
            chosen_l = min(recent_lows) if recent_lows else current_price - 1.5 * atr
            s_time = candles[-1].get("time", 0) if candles else 0

        half_w = max(0.25 * atr, chosen_l * 0.0008)
        u_p = min(chosen_l + half_w, current_price - 0.05 * atr)
        zone = {
            "center_price": round(chosen_l, decimals),
            "upper_price": round(u_p, decimals),
            "lower_price": round(chosen_l - half_w, decimals),
            "touches_count": 1,
            "average_bounce_atr": 1.0,
            "volume_confirmation": 0.5,
            "strength_score": 70.0,
            "status": "active",
            "zone_id": str(uuid.uuid4())[:8],
            "type": "support",
            "timeframe": interval,
            "first_detected_at": s_time,
            "last_tested_at": s_time,
            "smc_type": "STRUCTURE_ORIGIN",
            "smc_label": "OB Demand",
        }
        clean_supports.append(_add_legacy_fields(zone, current_price))

    if not clean_resistances:
        candidate_highs = [s for s in swings.get("highs", []) if s["price"] > current_price + 0.2 * atr]
        if candidate_highs:
            candidate_highs.sort(key=lambda s: s["time"], reverse=True)
            chosen_h = candidate_highs[0]["price"]
            r_time = candidate_highs[0].get("time", candles[-1]["time"] if candles else 0)
        else:
            recent_highs = [c["high"] for c in candles[-min(len(candles), 50):] if c["high"] > current_price + 0.2 * atr]
            chosen_h = max(recent_highs) if recent_highs else current_price + 1.5 * atr
            r_time = candles[-1].get("time", 0) if candles else 0

        half_w = max(0.25 * atr, chosen_h * 0.0008)
        l_p = max(chosen_h - half_w, current_price + 0.05 * atr)
        zone = {
            "center_price": round(chosen_h, decimals),
            "upper_price": round(chosen_h + half_w, decimals),
            "lower_price": round(l_p, decimals),
            "touches_count": 1,
            "average_bounce_atr": 1.0,
            "volume_confirmation": 0.5,
            "strength_score": 70.0,
            "status": "active",
            "zone_id": str(uuid.uuid4())[:8],
            "type": "resistance",
            "timeframe": interval,
            "first_detected_at": r_time,
            "last_tested_at": r_time,
            "smc_type": "STRUCTURE_ORIGIN",
            "smc_label": "OB Supply",
        }
        clean_resistances.append(_add_legacy_fields(zone, current_price))

    # Final re-sort to ensure correct order
    clean_resistances.sort(key=lambda r: r["price"])
    clean_supports.sort(key=lambda s: s["price"], reverse=True)

    # Cascade detection within closest resistances
    cascades: List[Dict[str, Any]] = []
    if len(clean_resistances) >= 2:
        r1, r2 = clean_resistances[0], clean_resistances[1]
        if r1["center_price"] > 0:
            diff = (r2["center_price"] - r1["center_price"]) / r1["center_price"] * 100
            if diff < 2.5 and r1.get("touches", 1) >= 1:
                cascades.append({
                    "type": "resistance_cascade",
                    "levels": [r1["price"], r2["price"]],
                    "desc": f"Каскад зон опору ({r1['price']}, {r2['price']})",
                    "distPct": r1["distPct"],
                })

    return {
        "currentPrice": current_price,
        "resistances": clean_resistances,
        "supports": clean_supports,
        "cascades": cascades,
        "pivot_points": pivots,
        "smc_summary": {
            "order_blocks_count": len(smc_obs),
            "liquidity_pools_count": len(smc_pools),
            "nearest_supply": clean_resistances[0]["price"] if clean_resistances else None,
            "nearest_demand": clean_supports[0]["price"] if clean_supports else None,
        }
    }



# ---------------------------------------------------------------------------
# Backward Compatibility Helpers (used by liquidity.py, structure.py)
# ---------------------------------------------------------------------------

def find_pivot_points(
    candles: List[Dict[str, Any]],
    left_bars: int = 3,
    right_bars: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """Finds swing highs and swing lows using rolling fractals."""
    return _find_swings(candles, left_bars=left_bars, right_bars=right_bars)


def cluster_levels(
    points: List[Dict[str, Any]],
    current_price: float,
    tolerance_pct: float = 0.3,
    min_thickness_ratio: float = 0.0015,
) -> List[Dict[str, Any]]:
    """Clusters nearby swing points into consolidated price zones."""
    if not points or current_price <= 0:
        return []

    sorted_pts = sorted(points, key=lambda x: x["price"])
    clusters: List[List[Dict[str, Any]]] = []

    for pt in sorted_pts:
        if not clusters:
            clusters.append([pt])
            continue

        curr_cluster = clusters[-1]
        avg_cluster_price = sum(p["price"] for p in curr_cluster) / len(curr_cluster)

        diff_pct = abs(pt["price"] - avg_cluster_price) / avg_cluster_price * 100
        if diff_pct <= tolerance_pct:
            curr_cluster.append(pt)
        else:
            clusters.append([pt])

    result = []
    for cluster in clusters:
        avg_price = sum(p["price"] for p in cluster) / len(cluster)
        min_p = min(p["price"] for p in cluster)
        max_p = max(p["price"] for p in cluster)
        touches = len(cluster)
        first_time = min(p["time"] for p in cluster)
        latest_time = max(p["time"] for p in cluster)

        min_thickness = avg_price * min_thickness_ratio
        if (max_p - min_p) < min_thickness:
            top = avg_price + (min_thickness / 2)
            bottom = avg_price - (min_thickness / 2)
        else:
            top = max_p
            bottom = min_p

        if current_price < bottom:
            dist_pct = ((bottom - current_price) / current_price) * 100
        elif current_price > top:
            dist_pct = ((top - current_price) / current_price) * 100
        else:
            dist_pct = 0.0

        decimals = 6 if avg_price < 1 else 4 if avg_price < 100 else 2
        result.append({
            "price": round(avg_price, decimals),
            "top": round(top, decimals),
            "bottom": round(bottom, decimals),
            "touches": touches,
            "distPct": round(dist_pct, 2),
            "firstTime": first_time,
            "latestTime": latest_time,
            "strength": min(touches, 5),
        })

    return result

