from typing import List, Dict, Any, Optional, Tuple
import math
import time
from .structure import analyze_market_structure

TIMEFRAME_SWING_CONFIG = {
    "1m":  {"left": 4, "right": 3, "prominence": 0.40},
    "3m":  {"left": 3, "right": 3, "prominence": 0.35},
    "5m":  {"left": 3, "right": 3, "prominence": 0.35},
    "15m": {"left": 3, "right": 3, "prominence": 0.35},
    "30m": {"left": 3, "right": 3, "prominence": 0.35},
    "1h":  {"left": 3, "right": 3, "prominence": 0.30},
    "4h":  {"left": 3, "right": 3, "prominence": 0.30},
    "1d":  {"left": 3, "right": 3, "prominence": 0.25},
}

TIMEFRAME_SECONDS_MAP = {
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


def _resolve_timeframe_step_seconds(
    candles: Optional[List[Dict[str, Any]]] = None,
    interval_str: Optional[str] = None,
    default_step: int = 3600,
) -> int:
    """Resolves candle duration in seconds from interval name or candle timestamps."""
    if interval_str:
        clean = interval_str.lower()
        if clean in TIMEFRAME_SECONDS_MAP:
            return TIMEFRAME_SECONDS_MAP[clean]

    if candles and len(candles) >= 2:
        diffs = [
            int(candles[i]["time"] - candles[i - 1]["time"])
            for i in range(1, min(10, len(candles)))
            if candles[i].get("time", 0) > candles[i - 1].get("time", 0)
        ]
        if diffs:
            return min(diffs)

    return default_step

# Configurable threshold for ATR Compression
DEFAULT_COMPRESSION_THRESHOLD = 0.65


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculate simple average true range over given period."""
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


def find_zigzag_swings(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    atr: float = 0.0,
    deviation_atr: float = 0.8,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    ATR-based ZigZag Swing Engine.
    Filters micro-noise by requiring a reversal of at least deviation_atr * ATR.
    Guarantees alternating high and low pivot points.
    """
    n = len(candles)
    if n < 5:
        return {"highs": [], "lows": []}

    if atr <= 0:
        atr = calculate_atr(candles, period=14)
    if atr <= 0:
        atr = max(candles[-1].get("close", 1.0) * 0.01, 0.0001)

    threshold = max(deviation_atr * atr, 0.0001)

    # State: 1 for seeking high, -1 for seeking low, 0 for initial
    state = 0
    candidate_high = {"price": candles[0]["high"], "time": candles[0]["time"], "index": 0, "volume": candles[0].get("volume", 0)}
    candidate_low = {"price": candles[0]["low"], "time": candles[0]["time"], "index": 0, "volume": candles[0].get("volume", 0)}

    raw_highs: List[Dict[str, Any]] = []
    raw_lows: List[Dict[str, Any]] = []

    for i in range(1, n):
        c = candles[i]
        h = c["high"]
        l = c["low"]

        if state == 0:
            if h - candidate_low["price"] >= threshold:
                raw_lows.append(candidate_low)
                candidate_high = {"price": h, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
                state = 1
            elif candidate_high["price"] - l >= threshold:
                raw_highs.append(candidate_high)
                candidate_low = {"price": l, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
                state = -1
            else:
                if h > candidate_high["price"]:
                    candidate_high = {"price": h, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
                if l < candidate_low["price"]:
                    candidate_low = {"price": l, "time": c["time"], "index": i, "volume": c.get("volume", 0)}

        elif state == 1:  # seeking high
            if h > candidate_high["price"]:
                candidate_high = {"price": h, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
            elif candidate_high["price"] - l >= threshold:
                raw_highs.append(candidate_high)
                candidate_low = {"price": l, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
                state = -1

        elif state == -1:  # seeking low
            if l < candidate_low["price"]:
                candidate_low = {"price": l, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
            elif h - candidate_low["price"] >= threshold:
                raw_lows.append(candidate_low)
                candidate_high = {"price": h, "time": c["time"], "index": i, "volume": c.get("volume", 0)}
                state = 1

    # Add final confirmed candidate if applicable
    if state == 1 and (not raw_highs or candidate_high["index"] > raw_highs[-1]["index"]):
        raw_highs.append(candidate_high)
    elif state == -1 and (not raw_lows or candidate_low["index"] > raw_lows[-1]["index"]):
        raw_lows.append(candidate_low)

    return {"highs": raw_highs, "lows": raw_lows}


def find_swings_for_trendlines(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    atr: float = 0.0,
    min_bar_gap: int = 3,
    use_zigzag: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Identifies high-significance Swing Highs and Swing Lows specifically for the given timeframe.
    Combines ATR-based ZigZag detection with left/right confirmation windows and volatility prominence.
    """
    n = len(candles)
    if n < 5:
        return {"highs": [], "lows": []}

    clean_tf = interval.lower()
    config = TIMEFRAME_SWING_CONFIG.get(clean_tf, {"left": 3, "right": 3, "prominence": 0.35})
    left_bars = min(config["left"], max(2, (n - 1) // 5))
    right_bars = min(config["right"], max(2, (n - 1) // 5))
    min_prominence_atr = config["prominence"]

    if atr <= 0:
        atr = calculate_atr(candles, period=14)
    if atr <= 0:
        atr = max(candles[-1].get("close", 1.0) * 0.01, 0.0001)

    raw_highs: List[Dict[str, Any]] = []
    raw_lows: List[Dict[str, Any]] = []

    for i in range(left_bars, n - right_bars):
        c = candles[i]
        curr_high = c["high"]
        curr_low = c["low"]

        # 1. Swing High check: strictly higher than neighbors
        is_high = all(candles[i - k]["high"] < curr_high for k in range(1, left_bars + 1)) and \
                  all(candles[i + k]["high"] < curr_high for k in range(1, right_bars + 1))

        if is_high:
            drop_left = curr_high - min(candles[i - k]["low"] for k in range(1, left_bars + 1))
            drop_right = curr_high - min(candles[i + k]["low"] for k in range(1, right_bars + 1))
            if min(drop_left, drop_right) < min_prominence_atr * atr:
                is_high = False

        # 2. Swing Low check: strictly lower than neighbors
        is_low = all(candles[i - k]["low"] > curr_low for k in range(1, left_bars + 1)) and \
                  all(candles[i + k]["low"] > curr_low for k in range(1, right_bars + 1))

        if is_low:
            rise_left = max(candles[i - k]["high"] for k in range(1, left_bars + 1)) - curr_low
            rise_right = max(candles[i + k]["high"] for k in range(1, right_bars + 1)) - curr_low
            if min(rise_left, rise_right) < min_prominence_atr * atr:
                is_low = False

        if is_high:
            raw_highs.append({
                "price": curr_high,
                "time": c["time"],
                "index": i,
                "volume": c.get("volume", 0),
            })
        if is_low:
            raw_lows.append({
                "price": curr_low,
                "time": c["time"],
                "index": i,
                "volume": c.get("volume", 0),
            })

    # Integrate ZigZag swings for structural macro-waves
    if use_zigzag:
        zz_res = find_zigzag_swings(candles, interval=clean_tf, atr=atr, deviation_atr=min_prominence_atr * 2.0)
        raw_highs.extend(zz_res["highs"])
        raw_lows.extend(zz_res["lows"])

    # Sort and filter out excessive clusters closer than min_bar_gap
    raw_highs.sort(key=lambda x: x["index"])
    raw_lows.sort(key=lambda x: x["index"])

    filtered_highs: List[Dict[str, Any]] = []
    for h in raw_highs:
        if not filtered_highs:
            filtered_highs.append(h)
        else:
            prev = filtered_highs[-1]
            if h["index"] - prev["index"] < min_bar_gap:
                if h["price"] > prev["price"]:
                    filtered_highs[-1] = h
            else:
                filtered_highs.append(h)

    filtered_lows: List[Dict[str, Any]] = []
    for l in raw_lows:
        if not filtered_lows:
            filtered_lows.append(l)
        else:
            prev = filtered_lows[-1]
            if l["index"] - prev["index"] < min_bar_gap:
                if l["price"] < prev["price"]:
                    filtered_lows[-1] = l
            else:
                filtered_lows.append(l)

    return {"highs": filtered_highs, "lows": filtered_lows}


def _collect_trendline_touches(
    candles: List[Dict[str, Any]],
    idx1: int,
    idx2: int,
    price1: float,
    slope: float,
    atr: float,
    is_res: bool,
) -> List[Dict[str, Any]]:
    """
    Collects confirmed touch events with timestamps, indices, and distances from the trendline ray.
    """
    n_candles = len(candles)
    touches = [
        {"index": idx1, "time": candles[idx1]["time"], "price": price1, "dist_atr": 0.0},
        {"index": idx2, "time": candles[idx2]["time"], "price": price1 + slope * (idx2 - idx1), "dist_atr": 0.0},
    ]
    last_touch_idx = idx2

    for k in range(idx1 + 1, n_candles):
        if k == idx2:
            continue
        if k - last_touch_idx < 3:
            continue

        c_k = candles[k]
        line_p = price1 + slope * (k - idx1)

        if is_res:
            dist = line_p - c_k["high"]
            if -0.25 * atr <= dist <= 0.35 * atr and c_k["close"] <= line_p + 0.25 * atr:
                touches.append({
                    "index": k,
                    "time": c_k["time"],
                    "price": c_k["high"],
                    "dist_atr": round(abs(dist) / max(atr, 1e-6), 3),
                })
                last_touch_idx = k
        else:
            dist = c_k["low"] - line_p
            if -0.25 * atr <= dist <= 0.35 * atr and c_k["close"] >= line_p - 0.25 * atr:
                touches.append({
                    "index": k,
                    "time": c_k["time"],
                    "price": c_k["low"],
                    "dist_atr": round(abs(dist) / max(atr, 1e-6), 3),
                })
                last_touch_idx = k

    touches.sort(key=lambda x: x["index"])
    return touches


def calculate_structural_quality(
    candles: List[Dict[str, Any]],
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    slope: float,
    atr: float,
    touches: List[Dict[str, Any]],
    is_res: bool,
) -> Tuple[float, Dict[str, float]]:
    """
    PHASE 1: Structural Quality (Q: 0 - 100)
    Measures purely objective geometric and structural integrity on the current bar:
    1. Anchor Prominence (0 - 30): swing depth relative to ATR.
    2. Spacing Regularity & Maturity (0 - 25): optimal span and touch intervals.
    3. Ray Precision (0 - 25): how tight contacts are to the mathematical ray.
    4. Void Integrity (0 - 20): absence of candle body intrusions.
    """
    n = len(candles)
    idx1, idx2 = p1["index"], p2["index"]
    p1_p = p1["price"]
    bar_dist = idx2 - idx1

    # 1. Anchor Prominence (0 - 30)
    c1, c2 = candles[idx1], candles[idx2]
    win = 4
    if is_res:
        min_l1 = min(candles[k]["low"] for k in range(max(0, idx1 - win), min(n, idx1 + win + 1)))
        min_l2 = min(candles[k]["low"] for k in range(max(0, idx2 - win), min(n, idx2 + win + 1)))
        prom1 = (c1["high"] - min_l1) / max(atr, 1e-6)
        prom2 = (c2["high"] - min_l2) / max(atr, 1e-6)
    else:
        max_h1 = max(candles[k]["high"] for k in range(max(0, idx1 - win), min(n, idx1 + win + 1)))
        max_h2 = max(candles[k]["high"] for k in range(max(0, idx2 - win), min(n, idx2 + win + 1)))
        prom1 = (max_h1 - c1["low"]) / max(atr, 1e-6)
        prom2 = (max_h2 - c2["low"]) / max(atr, 1e-6)

    avg_prom = (prom1 + prom2) / 2.0
    # Scaled: 0.5 ATR prominence gives ~10 pts, 2.0+ ATR gives full 30 pts
    prom_pts = min(30.0, max(5.0, (avg_prom / 2.0) * 30.0))

    # 2. Spacing Regularity & Maturity (0 - 25)
    # Span points (max 15): optimal between 10 and 60 bars
    if 10 <= bar_dist <= 60:
        span_pts = 15.0
    elif 6 <= bar_dist < 10 or 60 < bar_dist <= 90:
        span_pts = 10.0
    else:
        span_pts = 6.0

    # Spacing uniformity (max 10)
    if len(touches) >= 3:
        intervals = [touches[i]["index"] - touches[i - 1]["index"] for i in range(1, len(touches))]
        mean_int = sum(intervals) / len(intervals)
        var = sum((x - mean_int) ** 2 for x in intervals) / len(intervals)
        cv = math.sqrt(var) / max(mean_int, 1.0)
        uniformity_pts = max(2.0, 10.0 * (1.0 - min(cv, 0.8) / 0.8))
    else:
        uniformity_pts = 6.0  # neutral for 2 anchors

    spacing_pts = min(25.0, span_pts + uniformity_pts)

    # 3. Ray Precision (0 - 25)
    touch_dists = [t["dist_atr"] for t in touches if "dist_atr" in t]
    avg_dist = (sum(touch_dists) / len(touch_dists)) if touch_dists else 0.08
    # If touches hug the line within 0.1 ATR, full 25 pts. If 0.35 ATR, 5 pts.
    precision_pts = max(5.0, min(25.0, 25.0 * (1.0 - (avg_dist / 0.35) * 0.8)))

    # 4. Void Integrity (0 - 20)
    void_penalties = 0.0
    for k in range(idx1 + 1, idx2):
        c_k = candles[k]
        line_p = p1_p + slope * (k - idx1)
        if is_res:
            penetration = c_k["high"] - line_p
        else:
            penetration = line_p - c_k["low"]

        if penetration > 0.35 * atr:
            void_penalties += 4.0
        elif penetration > 0.15 * atr:
            void_penalties += 1.5

    void_pts = max(4.0, 20.0 - void_penalties)

    total_q = min(98.0, max(12.0, prom_pts + spacing_pts + precision_pts + void_pts))

    components = {
        "anchor_prominence": round(prom_pts, 1),
        "spacing_regularity": round(spacing_pts, 1),
        "ray_precision": round(precision_pts, 1),
        "void_integrity": round(void_pts, 1),
    }

    return round(total_q, 1), components


def evaluate_market_interaction_state(
    candles: List[Dict[str, Any]],
    p1: Dict[str, Any],
    slope: float,
    atr_series: List[float],
    is_res: bool,
    born_idx: int,
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
) -> Dict[str, Any]:
    """
    PHASE 2: Deterministic Market Interaction State Machine.
    Evaluated sequentially bar-by-bar from born_idx up to n-1 without look-ahead:
      APPROACHING, TESTING, REJECTED, COMPRESSION, BREAKOUT, RETEST, STALE
    """
    n = len(candles)
    idx1 = p1["index"]
    p1_p = p1["price"]

    current_state = "APPROACHING"
    previous_state = "APPROACHING"
    state_since_time = candles[born_idx]["time"] if born_idx < n else candles[-1]["time"]
    state_since_bar = born_idx
    has_broken_out = False
    breakout_bar = None
    last_interaction_bar = born_idx

    # Sequential bar-by-bar progression
    for k in range(born_idx, n):
        c = candles[k]
        atr_k = atr_series[k] if k < len(atr_series) and atr_series[k] > 0 else calculate_atr(candles[max(0, k-14):k+1], 14)
        if atr_k <= 0:
            atr_k = max(c["close"] * 0.01, 0.0001)

        line_p = p1_p + slope * (k - idx1)
        prev_state_before_bar = current_state

        # Distances relative to line
        if is_res:
            dist_close = line_p - c["close"]  # positive when under line
            is_breakout_close = c["close"] > line_p + 0.25 * atr_k
            is_rejection_close = dist_close >= 0.50 * atr_k
            is_touch_zone = (c["high"] >= line_p - 0.35 * atr_k and not is_breakout_close)
            is_near = abs(dist_close) <= 0.40 * atr_k
        else:
            dist_close = c["close"] - line_p  # positive when above line
            is_breakout_close = c["close"] < line_p - 0.25 * atr_k
            is_rejection_close = dist_close >= 0.50 * atr_k
            is_touch_zone = (c["low"] <= line_p + 0.35 * atr_k and not is_breakout_close)
            is_near = abs(dist_close) <= 0.40 * atr_k

        # Calculate local ATR compression
        sub5 = candles[max(0, k - 5): k + 1]
        sub20 = candles[max(0, k - 20): k + 1]
        a5 = calculate_atr(sub5, 5)
        a20 = calculate_atr(sub20, 20)
        is_compression = (a20 > 0 and (a5 / a20) < compression_threshold)

        # STATE TRANSITION RULES:
        next_state = current_state

        # 1. BREAKOUT has absolute priority once confirmed by close
        if is_breakout_close and not has_broken_out:
            next_state = "BREAKOUT"
            has_broken_out = True
            breakout_bar = k
            last_interaction_bar = k

        # 2. RETEST can ONLY occur after a confirmed BREAKOUT
        elif has_broken_out:
            # Check if price returns to test the broken line from the other side
            if is_res:
                # Broken resistance now tested from above
                if -0.35 * atr_k <= dist_close <= 0.40 * atr_k and c["low"] <= line_p + 0.35 * atr_k:
                    next_state = "RETEST"
                    last_interaction_bar = k
                elif (k - breakout_bar > 40) or (k - breakout_bar > 15 and c["close"] > line_p + 5.0 * atr_k):
                    next_state = "STALE"
            else:
                # Broken support now tested from below
                if -0.35 * atr_k <= dist_close <= 0.40 * atr_k and c["high"] >= line_p - 0.35 * atr_k:
                    next_state = "RETEST"
                    last_interaction_bar = k
                elif (k - breakout_bar > 40) or (k - breakout_bar > 15 and c["close"] < line_p - 5.0 * atr_k):
                    next_state = "STALE"

        # 3. Active line states (pre-breakout)
        else:
            # Check for STALE (no interaction for > 40 bars)
            if k - last_interaction_bar > 40:
                next_state = "STALE"
            # REJECTED requires confirmed reaction away from line
            elif current_state in ("TESTING", "COMPRESSION") and is_rejection_close:
                next_state = "REJECTED"
                last_interaction_bar = k
            elif is_touch_zone:
                last_interaction_bar = k
                if is_compression:
                    next_state = "COMPRESSION"
                else:
                    next_state = "TESTING"
            elif is_near and is_compression:
                next_state = "COMPRESSION"
                last_interaction_bar = k
            elif 0.35 * atr_k < dist_close <= 1.50 * atr_k:
                # Moving towards line check
                prev_c = candles[k - 1]
                prev_line = p1_p + slope * (k - 1 - idx1)
                prev_dist = (prev_line - prev_c["close"]) if is_res else (prev_c["close"] - prev_line)
                if dist_close < prev_dist:
                    next_state = "APPROACHING"
            elif is_near and is_compression:
                next_state = "COMPRESSION"
                last_interaction_bar = k
            elif 0.35 * atr_k < dist_close <= 1.50 * atr_k:
                # Moving towards line check
                prev_c = candles[k - 1]
                prev_line = p1_p + slope * (k - 1 - idx1)
                prev_dist = (prev_line - prev_c["close"]) if is_res else (prev_c["close"] - prev_line)
                if dist_close < prev_dist:
                    next_state = "APPROACHING"

        if next_state != current_state:
            previous_state = current_state
            current_state = next_state
            state_since_time = c["time"]
            state_since_bar = k

    return {
        "current_state": current_state,
        "previous_state": previous_state,
        "state_since_time": state_since_time,
        "state_since_bar": state_since_bar,
        "has_broken_out": has_broken_out,
        "last_interaction_bar": last_interaction_bar,
    }


def evaluate_htf_structural_context(
    line_type: str,
    candle_time: int,
    htf_candles: Optional[List[Dict[str, Any]]] = None,
    evaluation_time: Optional[int] = None,
    is_candle_closed: bool = False,
    ltf_interval: Optional[str] = None,
) -> str:
    """
    Evaluates Higher-Timeframe (HTF) market structure context for a lower-timeframe trendline.
    Strictly enforces the Point-in-Time invariant:
      htf_candle_close_time <= evaluation_time

    - An HTF candle is ONLY included after it is fully closed.
    - An unclosed / forming HTF candle is strictly excluded.
    - If evaluation_time is not provided:
        * If is_candle_closed is True: evaluation_time = candle_time + ltf_step
        * If is_candle_closed is False: evaluation_time = candle_time

    Returns:
      'ALIGNED': Support line in BULLISH HTF, or Resistance line in BEARISH HTF.
      'AGAINST_HTF': Support line in BEARISH HTF, or Resistance line in BULLISH HTF.
      'NEUTRAL': HTF trend is NEUTRAL / CONSOLIDATING / EXPANDING.
      'UNAVAILABLE': Missing or insufficient (< 20 closed bars) HTF candle history.
    """
    if not htf_candles or len(htf_candles) < 20:
        return "UNAVAILABLE"

    # 1. Determine effective evaluation time
    if evaluation_time is not None:
        effective_eval_time = int(evaluation_time)
    elif is_candle_closed:
        ltf_step = _resolve_timeframe_step_seconds(interval_str=ltf_interval, default_step=900)
        effective_eval_time = int(candle_time + ltf_step)
    else:
        effective_eval_time = int(candle_time)

    # 2. Determine HTF candle step duration
    htf_step = _resolve_timeframe_step_seconds(candles=htf_candles, default_step=3600)

    # 3. Strict Point-in-Time filter: htf_candle_close_time <= effective_eval_time
    pit_htf = [
        c for c in htf_candles
        if int(c.get("close_time") or (c.get("time", 0) + htf_step)) <= effective_eval_time
    ]
    if len(pit_htf) < 20:
        return "UNAVAILABLE"

    htf_struct = analyze_market_structure(pit_htf)
    htf_trend = htf_struct.get("trend", "NEUTRAL")

    is_res = (line_type == "resistance_trendline")

    if htf_trend == "BULLISH":
        return "AGAINST_HTF" if is_res else "ALIGNED"
    elif htf_trend == "BEARISH":
        return "ALIGNED" if is_res else "AGAINST_HTF"
    else:
        return "NEUTRAL"


def compute_structural_risk_flags(
    htf_context: str,
    interaction_state: str,
    compression_ratio: float,
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
    status: str = "ACTIVE",
) -> List[str]:
    """
    Assembles active structural risk flags for the trendline.
    Multiple flags can coexist without overriding each other.
    Allowed flags: 'AGAINST_HTF', 'COMPRESSION', 'BREAKOUT', 'RETEST', 'STALE'.
    """
    flags: List[str] = []

    if htf_context == "AGAINST_HTF":
        flags.append("AGAINST_HTF")

    if interaction_state == "COMPRESSION" or compression_ratio < compression_threshold:
        flags.append("COMPRESSION")

    if interaction_state == "BREAKOUT" or status == "BROKEN":
        flags.append("BREAKOUT")

    if interaction_state == "RETEST":
        flags.append("RETEST")

    if interaction_state == "STALE" or status == "STALE":
        flags.append("STALE")

    return flags


def _evaluate_trendline_candidate(
    candles: List[Dict[str, Any]],
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    tl_type: str,
    interval: str,
    atr: float,
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
    htf_candles: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates a candidate line connecting two swing points (p1, p2).
    Computes Structural Quality (Q), Market Interaction State Machine, and Touch Context.
    """
    idx1, idx2 = p1["index"], p2["index"]
    if idx2 <= idx1:
        return None

    bar_dist = idx2 - idx1
    if bar_dist < 4:
        return None

    price1 = p1["price"]
    price2 = p2["price"]
    is_res = (tl_type == "resistance_trendline")
    n_candles = len(candles)

    # Dynamic precision based on price magnitude so micro-cap coins like PUMP (0.0037) aren't truncated
    if price1 >= 1000.0:
        precision = 1
    elif price1 >= 1.0:
        precision = 2
    elif price1 >= 0.01:
        precision = 4
    elif price1 >= 0.0001:
        precision = 6
    else:
        precision = 8

    p1_price = round(price1, precision)
    p2_price = round(price2, precision)
    slope_precision = max(6, precision + 2)
    slope = round((p2_price - p1_price) / bar_dist, slope_precision)

    if is_res:
        if p1_price <= p2_price:
            return None
        diff = p1_price - p2_price
    else:
        if p2_price <= p1_price:
            return None
        diff = p2_price - p1_price

    abs_slope = abs(slope)
    if diff < 0.35 * atr or abs_slope < 0.02 * atr or abs_slope > 1.6 * atr:
        return None

    # Geometrical validity between idx1 and idx2:
    # Candle bodies must not penetrate the line between anchors
    for k in range(idx1 + 1, idx2):
        c_k = candles[k]
        line_p = p1_price + slope * (k - idx1)
        if is_res:
            if c_k["close"] > line_p + 0.25 * atr or c_k["high"] > line_p + 0.6 * atr:
                return None
        else:
            if c_k["close"] < line_p - 0.25 * atr or c_k["low"] < line_p - 0.6 * atr:
                return None

    # 1. Collect all confirmed point-in-time touch events
    touches = _collect_trendline_touches(candles, idx1, idx2, p1_price, slope, atr, is_res)
    touch_count = len(touches)

    # 2. PHASE 1: Structural Quality (Q: 0 - 100) & Components
    q_score, q_components = calculate_structural_quality(
        candles=candles,
        p1=p1,
        p2=p2,
        slope=slope,
        atr=atr,
        touches=touches,
        is_res=is_res,
    )

    # 3. PHASE 2: Market Interaction State Machine
    clean_tf = interval.lower()
    config = TIMEFRAME_SWING_CONFIG.get(clean_tf, {"left": 3, "right": 3})
    born_idx = min(n_candles - 1, idx2 + config.get("right", 3))

    # Pre-calculate rolling ATR series for sequential bar analysis
    atr_series = []
    for k in range(n_candles):
        sub = candles[max(0, k - 14): k + 1]
        atr_series.append(calculate_atr(sub, 14))

    fsm_res = evaluate_market_interaction_state(
        candles=candles,
        p1=p1,
        slope=slope,
        atr_series=atr_series,
        is_res=is_res,
        born_idx=born_idx,
        compression_threshold=compression_threshold,
    )

    interaction_state = fsm_res["current_state"]
    previous_state = fsm_res["previous_state"]
    interaction_state_since = fsm_res["state_since_time"]

    # Map state machine outcome to high-level legacy status for backward compatibility
    if fsm_res["has_broken_out"] or interaction_state == "BREAKOUT":
        status = "BROKEN"
    elif interaction_state == "STALE":
        status = "STALE"
    elif (n_candles - 1 - idx2) < 3 and touch_count <= 2:
        status = "FORMING"
    else:
        status = "ACTIVE"

    # 4. PHASE 4: Touch Context Metrics
    curr_c = candles[-1]
    latest_line_p = p1_price + slope * (n_candles - 1 - idx1)
    dist_signed = (curr_c["close"] - latest_line_p) if is_res else (curr_c["close"] - latest_line_p)
    dist_atr = round(dist_signed / max(atr, 1e-6), 3)

    # Spacing between touches
    if len(touches) >= 2:
        intervals = [touches[i]["index"] - touches[i - 1]["index"] for i in range(1, len(touches))]
        touch_spacing_bars = round(sum(intervals) / len(intervals), 1)
    else:
        touch_spacing_bars = float(bar_dist)

    last_touch_time = touches[-1]["time"] if touches else p2["time"]

    # Compression ratio: ATR(5) / ATR(20) on current bar
    sub5 = candles[max(0, n_candles - 5):]
    sub20 = candles[max(0, n_candles - 20):]
    atr5 = calculate_atr(sub5, 5)
    atr20 = calculate_atr(sub20, 20)
    compression_ratio = round(atr5 / atr20, 3) if atr20 > 0 else 1.0

    # Arrival Velocity (speed of approach over last 3 bars in ATR / bar)
    if n_candles >= 4:
        c_prev3 = candles[-4]
        lp_prev3 = p1_price + slope * (n_candles - 4 - idx1)
        prev_dist = abs(c_prev3["close"] - lp_prev3)
        curr_dist = abs(curr_c["close"] - latest_line_p)
        velocity = round((prev_dist - curr_dist) / (3.0 * max(atr, 1e-6)), 3)
    else:
        velocity = 0.0

    last_updated = int(curr_c.get("time", 0))
    is_closed = bool(curr_c.get("is_closed", True))
    explicit_eval_time = curr_c.get("evaluation_time")

    # Phase 4.6: Strict Point-in-Time HTF Structural Context & Structural Risk Flags
    htf_context = evaluate_htf_structural_context(
        line_type=tl_type,
        candle_time=last_updated,
        htf_candles=htf_candles,
        evaluation_time=explicit_eval_time,
        is_candle_closed=is_closed,
        ltf_interval=interval,
    )
    structural_risk_flags = compute_structural_risk_flags(
        htf_context=htf_context,
        interaction_state=interaction_state,
        compression_ratio=compression_ratio,
        compression_threshold=compression_threshold,
        status=status,
    )

    is_confirmed = (touch_count >= 3)
    confirmation_status = "CONFIRMED" if is_confirmed else "FORMING"

    label_side = "Опір" if is_res else "Підтримка"
    label = f"Наклонка ({label_side})"
    timeframe_label = f"Наклонка ({label_side}) [{interval}]"
    if touch_count > 2:
        timeframe_label += f" (x{touch_count} Підтверджена)"
    else:
        timeframe_label += f" (x{touch_count})"

    direction = "DESCENDING" if is_res else "ASCENDING"

    return {
        "timeframe": interval,
        "direction": direction,
        "line_type": tl_type,
        "start_point": {
            "time": int(p1["time"]),
            "price": p1_price,
            "index": int(idx1),
        },
        "end_point": {
            "time": int(p2["time"]),
            "price": p2_price,
            "index": int(idx2),
        },
        "slope": slope,
        "touch_count": int(touch_count),
        "is_confirmed": is_confirmed,
        "isConfirmed": is_confirmed,
        "confirmation_status": confirmation_status,
        "confirmationStatus": confirmation_status,
        "touches_rule": "3_PLUS_TOUCHES" if is_confirmed else "2_TOUCH_PROVISIONAL",
        "strength": q_score,
        "status": status,
        "last_updated": last_updated,

        # New Structural Intelligence Specification:
        "structural_quality": q_score,
        "structural_quality_components": q_components,
        "interaction_state": interaction_state,
        "interaction_state_since": int(interaction_state_since),
        "previous_interaction_state": previous_state,
        "last_confirmed_touch": int(last_touch_time),
        "touch_spacing_bars": touch_spacing_bars,
        "distance_to_line_atr": dist_atr,
        "compression_ratio": compression_ratio,
        "arrival_velocity": velocity,

        # CamelCase aliases for Frontend compatibility:
        "structuralQuality": q_score,
        "structuralQualityComponents": q_components,
        "interactionState": interaction_state,
        "interactionStateSince": int(interaction_state_since),
        "previousInteractionState": previous_state,
        "touchCount": int(touch_count),
        "lastConfirmedTouch": int(last_touch_time),
        "touchSpacingBars": touch_spacing_bars,
        "distanceToLineAtr": dist_atr,
        "compressionRatio": compression_ratio,
        "arrivalVelocity": velocity,

        # Phase 4: HTF Structural Context & Structural Risk Flags:
        "htf_context": htf_context,
        "htfContext": htf_context,
        "structural_risk_flags": structural_risk_flags,
        "structuralRiskFlags": structural_risk_flags,

        # Backward compatibility fields for chart and screener
        "id": f"tl-{interval}-{ 'res' if is_res else 'sup' }-{p1['time']}-{p2['time']}",
        "type": tl_type,
        "label": label,
        "timeframe_label": timeframe_label,
        "p1": {"time": int(p1["time"]), "price": p1_price},
        "p2": {"time": int(p2["time"]), "price": p2_price},
        "score": q_score,
        "touches": int(touch_count),
    }


def detect_timeframe_trendlines(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    include_broken: bool = False,
    max_lines_per_type: int = 1,
    htf_candles: Optional[List[Dict[str, Any]]] = None,
    require_three_touches: bool = False,
) -> List[Dict[str, Any]]:
    """
    Independently detects and builds trendlines strictly from the candle history of the specified timeframe.
    Prioritizes high-significance 3+ touch confirmed lines.
    Returns the top high-quality trendlines without visual duplicate lines.
    """
    if len(candles) < 8:
        return []

    atr = calculate_atr(candles, period=14)
    if atr <= 0:
        atr = max(candles[-1].get("close", 1.0) * 0.01, 0.0001)

    swings = find_swings_for_trendlines(candles, interval=interval, atr=atr)
    highs = swings["highs"]
    lows = swings["lows"]

    recent_highs = highs[-10:] if len(highs) >= 10 else highs
    recent_lows = lows[-10:] if len(lows) >= 10 else lows

    # 1. Resistance trendline candidates
    res_candidates: List[Dict[str, Any]] = []
    for i in range(len(recent_highs) - 1):
        for j in range(i + 1, len(recent_highs)):
            candidate = _evaluate_trendline_candidate(
                candles=candles,
                p1=recent_highs[i],
                p2=recent_highs[j],
                tl_type="resistance_trendline",
                interval=interval,
                atr=atr,
                htf_candles=htf_candles,
            )
            if candidate:
                if not include_broken and candidate["status"] == "BROKEN":
                    continue
                res_candidates.append(candidate)

    # 2. Support trendline candidates
    sup_candidates: List[Dict[str, Any]] = []
    for i in range(len(recent_lows) - 1):
        for j in range(i + 1, len(recent_lows)):
            candidate = _evaluate_trendline_candidate(
                candles=candles,
                p1=recent_lows[i],
                p2=recent_lows[j],
                tl_type="support_trendline",
                interval=interval,
                atr=atr,
                htf_candles=htf_candles,
            )
            if candidate:
                if not include_broken and candidate["status"] == "BROKEN":
                    continue
                sup_candidates.append(candidate)

    if require_three_touches:
        res_candidates = [c for c in res_candidates if c.get("is_confirmed", False)]
        sup_candidates = [c for c in sup_candidates if c.get("is_confirmed", False)]

    # Sort candidates prioritizing confirmed lines (3+ touches), active status, and structural quality
    res_candidates.sort(
        key=lambda x: (
            x.get("is_confirmed", False),
            x["status"] == "ACTIVE",
            x.get("touch_count", 0),
            x["structural_quality"]
        ),
        reverse=True
    )
    sup_candidates.sort(
        key=lambda x: (
            x.get("is_confirmed", False),
            x["status"] == "ACTIVE",
            x.get("touch_count", 0),
            x["structural_quality"]
        ),
        reverse=True
    )

    # Deduplicate: avoid near-identical parallel lines
    def deduplicate(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for cand in candidates:
            overlap = False
            for sel in selected:
                slope_diff = abs(cand["slope"] - sel["slope"]) / max(abs(sel["slope"]), 1e-6)
                price_diff = abs(cand["start_point"]["price"] - sel["start_point"]["price"])
                if slope_diff < 0.25 and price_diff < 1.0 * atr:
                    overlap = True
                    break
            if not overlap:
                selected.append(cand)
                if len(selected) >= max_lines_per_type:
                    break
        return selected

    best_res = deduplicate(res_candidates)
    best_sup = deduplicate(sup_candidates)

    return best_res + best_sup


def calculate_linear_regression_channel(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    lookback: int = 60,
    num_std: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """
    Computes Linear Regression Trendline and Channel using Ordinary Least Squares (OLS).
    Formula:
      y = k * x + b
      k = Cov(x, y) / Var(x) = [ sum((x - mean(x)) * (y - mean(y))) ] / [ sum((x - mean(x))^2) ]
      b = mean(y) - k * mean(x)
      R^2 = 1 - (SS_res / SS_tot)
      Upper/Lower bounds = y ± num_std * std_dev(residuals)
    """
    n_candles = len(candles)
    if n_candles < 10:
        return None

    sample_size = min(n_candles, max(15, lookback))
    sample = candles[-sample_size:]
    N = len(sample)

    y_values = [float(c["close"]) for c in sample]
    x_mean = (N - 1) / 2.0
    y_mean = sum(y_values) / N

    cov_xy = 0.0
    var_x = 0.0
    ss_tot = 0.0

    for i in range(N):
        dx = i - x_mean
        dy = y_values[i] - y_mean
        cov_xy += dx * dy
        var_x += dx * dx
        ss_tot += dy * dy

    if var_x == 0.0:
        return None

    k = cov_xy / var_x
    b = y_mean - k * x_mean

    ss_res = 0.0
    for i in range(N):
        pred_y = k * i + b
        diff = y_values[i] - pred_y
        ss_res += diff * diff

    sigma = math.sqrt(ss_res / N)
    if sigma < 1e-6:
        atr_sample = calculate_atr(sample, 14)
        sigma = atr_sample if atr_sample > 0 else max(curr_price * 0.005, 0.01)

    r_squared = (1.0 - (ss_res / ss_tot)) if ss_tot > 1e-9 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    p1_time = int(sample[0]["time"])
    p2_time = int(sample[-1]["time"])

    start_mid = b
    end_mid = k * (N - 1) + b

    start_upper = start_mid + num_std * sigma
    end_upper = end_mid + num_std * sigma

    start_lower = start_mid - num_std * sigma
    end_lower = end_mid - num_std * sigma

    curr_price = y_values[-1]
    channel_width = end_upper - end_lower
    if channel_width > 1e-6:
        channel_pos_pct = round(((curr_price - end_lower) / channel_width) * 100.0, 1)
    else:
        channel_pos_pct = 50.0

    if k > 0.0001 and r_squared >= 0.15:
        direction = "ASCENDING"
    elif k < -0.0001 and r_squared >= 0.15:
        direction = "DESCENDING"
    else:
        direction = "FLAT"

    price_precision = 2 if curr_price >= 1.0 else (4 if curr_price >= 0.01 else 6)
    slope_precision = price_precision + 2

    return {
        "id": f"regchan-{interval.lower()}-{p1_time}-{p2_time}",
        "timeframe": interval,
        "slope": round(k, slope_precision),
        "intercept": round(b, price_precision),
        "r_squared": round(r_squared, 3),
        "rSquared": round(r_squared, 3),
        "std_dev": round(sigma, price_precision),
        "stdDev": round(sigma, price_precision),
        "num_std": num_std,
        "numStd": num_std,
        "direction": direction,
        "sample_size": N,
        "channel_position_pct": channel_pos_pct,
        "channelPositionPct": channel_pos_pct,
        "start_time": p1_time,
        "end_time": p2_time,
        "middle": {
            "p1": {"time": p1_time, "price": round(start_mid, price_precision)},
            "p2": {"time": p2_time, "price": round(end_mid, price_precision)},
        },
        "upper": {
            "p1": {"time": p1_time, "price": round(start_upper, price_precision)},
            "p2": {"time": p2_time, "price": round(end_upper, price_precision)},
        },
        "lower": {
            "p1": {"time": p1_time, "price": round(start_lower, price_precision)},
            "p2": {"time": p2_time, "price": round(end_lower, price_precision)},
        },
    }
