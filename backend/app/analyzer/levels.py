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
from typing import List, Dict, Any

INTERVAL_CONFIG = {
    "1m":  {"left": 5, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "3m":  {"left": 5, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "5m":  {"left": 5, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "15m": {"left": 5, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "30m": {"left": 4, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "1h":  {"left": 4, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "2h":  {"left": 4, "right": 4, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "4h":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
    "1d":  {"left": 4, "right": 3, "atr_period": 14, "max_zones": 3, "min_spacing_atr": 2.2, "prominence": 0.5},
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
    zone["firstTime"] = zone["first_detected_at"]
    zone["latestTime"] = zone["last_tested_at"]
    zone["distPct"] = round(dist_pct, 2)
    zone["strength"] = int(min(zone.get("strength_score", 0) / 20, 5))
    return zone


# ---------------------------------------------------------------------------
# Public API: analyze_levels
# ---------------------------------------------------------------------------

def analyze_levels(candles: List[Dict[str, Any]], interval: str = "5m") -> Dict[str, Any]:
    """
    Analyzes candlestick data and returns confirmed support/resistance zones.
    Rules:
    - Support is strictly below current price (GREEN).
    - Resistance is strictly above current price (RED).
    - Zones are valid ONLY if confirmed by at least 2 independent touches/reactions (touches_count >= 2).
    - Single swings are noise and filtered out.
    - S/R role reversals (flips) are marked with status='retested'.
    """
    if not candles:
        return {"currentPrice": 0.0, "resistances": [], "supports": [], "cascades": []}

    clean_interval = interval.lower()
    cfg = INTERVAL_CONFIG.get(clean_interval, INTERVAL_CONFIG["5m"])

    left_bars: int = cfg["left"]
    right_bars: int = cfg["right"]
    atr_period: int = cfg["atr_period"]
    max_zones: int = cfg["max_zones"]

    current_price: float = candles[-1]["close"]
    n = len(candles)

    # Step 1 – ATR
    atr = _calculate_atr(candles, atr_period)
    if atr <= 0:
        atr = current_price * 0.001

    # Step 2 – Swing highs and lows with prominence
    prominence = cfg.get("prominence", 0.5)
    swings = _find_swings(candles, left_bars, right_bars, atr=atr, min_prominence_atr=prominence)
    all_swings = swings["highs"] + swings["lows"]
    if not all_swings:
        return {"currentPrice": current_price, "resistances": [], "supports": [], "cascades": []}

    # Step 3 – Cluster swings into zones using ATR proximity
    raw_zones = _cluster_swings(all_swings, atr)

    confirmed_resistances: List[Dict[str, Any]] = []
    confirmed_supports: List[Dict[str, Any]] = []

    for zone in raw_zones:
        center = zone["center_price"]
        zone_type = "resistance" if center >= current_price else "support"

        # Skip micro-noise right on the current candle (< 0.4 ATR)
        dist_atr = abs(center - current_price) / atr
        if dist_atr < 0.4:
            continue

        # Step 4 – Count independent touches (reactions)
        zone = _count_touches(zone, candles, zone_type)

        # CRITICAL: A zone is only valid if confirmed (touches >= 2)
        if zone["touches_count"] < 2:
            continue

        # Step 5 – Measure average bounce strength
        avg_bounce = _measure_bounces(zone, candles, zone_type, atr)
        zone["average_bounce_atr"] = round(avg_bounce, 2)

        # Step 6 – Volume confirmation
        avg_vol = sum(c.get("volume", 0) for c in candles) / max(n, 1)
        touch_vols = zone.get("_touch_volumes", [])
        if touch_vols:
            above_avg = sum(1 for v in touch_vols if v >= avg_vol)
            zone["volume_confirmation"] = round(above_avg / len(touch_vols), 2)
        else:
            zone["volume_confirmation"] = 0.5

        # Step 7 – Strength score (0-100)
        score = _compute_strength_score(zone, candles, zone_type, avg_bounce, atr)
        zone["strength_score"] = score

        # Step 8 – Role reversal & status
        cluster_swings = zone.get("_swings", [])
        has_highs = any(s in swings["highs"] for s in cluster_swings)
        has_lows = any(s in swings["lows"] for s in cluster_swings)

        last_time = zone["last_tested_at"]
        last_idx = next((i for i, c in reversed(list(enumerate(candles))) if c["time"] <= last_time), 0)
        is_old = (n - 1 - last_idx) > 0.5 * n

        if is_old:
            status = "weakening"
        elif (zone_type == "resistance" and has_lows and not has_highs) or (zone_type == "support" and has_highs and not has_lows):
            status = "retested"
        else:
            status = "active"

        zone["status"] = status
        zone["zone_id"] = str(uuid.uuid4())[:8]
        zone["type"] = zone_type
        zone["timeframe"] = interval

        # Step 9 – Round prices & add legacy fields
        decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2
        for field in ("center_price", "upper_price", "lower_price"):
            zone[field] = round(zone[field], decimals)

        zone = _add_legacy_fields(zone, current_price)

        # Cleanup internal keys
        for key in ("_swings", "_touch_volumes", "_first_idx", "_last_idx"):
            zone.pop(key, None)

        if zone_type == "resistance":
            confirmed_resistances.append(zone)
        else:
            confirmed_supports.append(zone)

    # Step 10 – Key Zone Selection with strict spacing enforcement:
    # Only keep the top max_zones primary levels that have at least min_spacing_atr between them
    min_spacing_atr = cfg.get("min_spacing_atr", 2.2)

    def _select_key_zones(z_list: List[Dict[str, Any]], max_n: int, min_sep: float) -> List[Dict[str, Any]]:
        # Sort closest to current price first
        z_list.sort(key=lambda z: abs(z["center_price"] - current_price))
        selected = []
        for z in z_list:
            # Must be well-spaced from any already selected zone
            if any(abs(z["center_price"] - sz["center_price"]) < min_sep * atr for sz in selected):
                continue
            selected.append(z)
            if len(selected) >= max_n:
                break
        return selected

    clean_resistances = _select_key_zones(confirmed_resistances, max_zones, min_spacing_atr)
    clean_supports = _select_key_zones(confirmed_supports, max_zones, min_spacing_atr)

    # Dynamic Discovery: When price breaks the last available support on this timeframe,
    # find the newly formed extreme swing that marks the new boundary on this timeframe
    if not clean_supports and swings["lows"]:
        candidate_lows = [s for s in swings["lows"] if s["price"] < current_price]
        if candidate_lows:
            candidate_lows.sort(key=lambda s: s["time"], reverse=True)
            new_s = candidate_lows[0]
            center = new_s["price"]
            half_w = 0.35 * atr
            zone = {
                "center_price": center,
                "upper_price": center + half_w,
                "lower_price": center - half_w,
                "touches_count": 1,
                "average_bounce_atr": 1.0,
                "volume_confirmation": 0.5,
                "strength_score": 50.0,
                "status": "active",
                "zone_id": str(uuid.uuid4())[:8],
                "type": "support",
                "timeframe": interval,
            }
            decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2
            for f in ("center_price", "upper_price", "lower_price"):
                zone[f] = round(zone[f], decimals)
            clean_supports.append(_add_legacy_fields(zone, current_price))

    # Dynamic Discovery for resistance: when price breaks the last available resistance on this timeframe
    if not clean_resistances and swings["highs"]:
        candidate_highs = [s for s in swings["highs"] if s["price"] > current_price]
        if candidate_highs:
            candidate_highs.sort(key=lambda s: s["time"], reverse=True)
            new_r = candidate_highs[0]
            center = new_r["price"]
            half_w = 0.35 * atr
            zone = {
                "center_price": center,
                "upper_price": center + half_w,
                "lower_price": center - half_w,
                "touches_count": 1,
                "average_bounce_atr": 1.0,
                "volume_confirmation": 0.5,
                "strength_score": 50.0,
                "status": "active",
                "zone_id": str(uuid.uuid4())[:8],
                "type": "resistance",
                "timeframe": interval,
            }
            decimals = 6 if current_price < 1 else 4 if current_price < 100 else 2
            for f in ("center_price", "upper_price", "lower_price"):
                zone[f] = round(zone[f], decimals)
            clean_resistances.append(_add_legacy_fields(zone, current_price))

    # Step 11 – Cascade detection within closest resistances
    cascades: List[Dict[str, Any]] = []
    if len(clean_resistances) >= 2:
        r1, r2 = clean_resistances[0], clean_resistances[1]
        if r1["center_price"] > 0:
            diff = (r2["center_price"] - r1["center_price"]) / r1["center_price"] * 100
            if diff < 2.5 and r1["touches"] >= 2:
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

