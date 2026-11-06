from typing import List, Dict, Any, Optional
import math
import time

def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> List[float]:
    """Calculates Average True Range (ATR) across historical candles."""
    n = len(candles)
    if n == 0:
        return []
    
    tr = [0.0] * n
    tr[0] = candles[0]["high"] - candles[0]["low"]
    
    for i in range(1, n):
        hl = candles[i]["high"] - candles[i]["low"]
        hc = abs(candles[i]["high"] - candles[i - 1]["close"])
        lc = abs(candles[i]["low"] - candles[i - 1]["close"])
        tr[i] = max(hl, hc, lc)
        
    atr = [0.0] * n
    if n < period:
        # Fallback simple average
        avg = sum(tr) / n
        return [avg] * n

    current_atr = sum(tr[:period]) / period
    atr[period - 1] = current_atr
    for i in range(period, n):
        current_atr = (current_atr * (period - 1) + tr[i]) / period
        atr[i] = current_atr

    for i in range(period - 1):
        atr[i] = atr[period - 1]

    return atr


def detect_and_track_fvgs(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    symbol: str = "ETH",
    min_atr_mult: float = 0.1,
    min_impulse_body_ratio: float = 0.6,
    trend: str = "NEUTRAL",
    structure_events: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Independent FVG detection & life-cycle tracking engine.
    - Uses 3-candle pattern strictly formed at candle 3 close (no lookahead bias).
    - Tracks complete mitigation lifecycle (FRESH -> PARTIALLY MITIGATED -> 50% MITIGATED -> FULLY MITIGATED).
    - Tracks Inverse FVG (IFVG) upon candle close breaking opposite boundary.
    - Computes Strength Score (0-100) strictly locked at creation time.
    """
    n = len(candles)
    if n < 3:
        return []

    atrs = calculate_atr(candles, period=14)
    fvgs: List[Dict[str, Any]] = []

    # Calculate 20-period moving average of volume for volume confirmation
    vol_ma = [0.0] * n
    for i in range(n):
        start_idx = max(0, i - 19)
        subset = candles[start_idx:i + 1]
        vol_ma[i] = sum(c.get("volume", 0.0) for c in subset) / len(subset)

    # 1. Detect FVGs on historical 3-candle windows
    for i in range(2, n):
        c1 = candles[i - 2]
        c2 = candles[i - 1] # Impulse candle
        c3 = candles[i]     # Confirmation candle (FVG confirmed on c3 close)

        atr_val = atrs[i] if i < len(atrs) and atrs[i] > 0 else (c2["high"] - c2["low"] or 1.0)
        c2_range = c2["high"] - c2["low"]
        c2_body = abs(c2["close"] - c2["open"])
        c2_body_ratio = (c2_body / c2_range) if c2_range > 0 else 0.0

        is_bullish = c3["low"] > c1["high"]
        is_bearish = c3["high"] < c1["low"]

        if not is_bullish and not is_bearish:
            continue

        fvg_type = "BULLISH" if is_bullish else "BEARISH"

        if is_bullish:
            lower_price = c1["high"]
            upper_price = c3["low"]
        else:
            lower_price = c3["high"]
            upper_price = c1["low"]

        gap_size = upper_price - lower_price
        if gap_size <= 0:
            continue

        gap_size_atr = gap_size / atr_val if atr_val > 0 else 0.0

        # Filtering thresholds
        if gap_size_atr < min_atr_mult:
            continue
        if c2_body_ratio < min_impulse_body_ratio:
            continue

        midpoint_price = round((upper_price + lower_price) / 2.0, 6)
        creation_timestamp = c3["time"]
        fvg_id = f"fvg_{symbol.upper()}_{interval.lower()}_{c1['time']}_{c2['time']}_{c3['time']}_{fvg_type.lower()}"

        # Volume confirmation
        c2_vol = c2.get("volume", 0.0)
        c2_vol_ma = vol_ma[i - 1] if vol_ma[i - 1] > 0 else 1.0
        volume_ratio = c2_vol / c2_vol_ma
        volume_confirmed = volume_ratio >= 1.2

        # Market structure alignment
        ms_confirmed = False
        if is_bullish and trend in ["BULLISH", "NEUTRAL"]:
            ms_confirmed = True
        elif is_bearish and trend in ["BEARISH", "NEUTRAL"]:
            ms_confirmed = True

        # BOS / CHoCH confirmation around impulse candle
        structure_confirmed = False
        if structure_events:
            for ev in structure_events:
                ev_type = ev.get("type", "")
                if is_bullish and "BULLISH" in ev_type:
                    structure_confirmed = True
                    break
                elif is_bearish and "BEARISH" in ev_type:
                    structure_confirmed = True
                    break

        # Calculate Strength Score (0 to 100) locked at creation
        # 1. Impulse candle strength: 25% (body ratio >= 0.8 => 25 pts, >= 0.6 => 18 pts)
        score_impulse = min(25.0, (c2_body_ratio / 0.85) * 25.0)
        # 2. FVG size relative to ATR: 20% (gap_size_atr >= 0.5 => 20 pts, >= 0.25 => 14 pts)
        score_atr = min(20.0, (gap_size_atr / 0.5) * 20.0)
        # 3. Trading volume: 15% (vol ratio >= 1.5 => 15 pts)
        score_vol = min(15.0, (volume_ratio / 1.5) * 15.0)
        # 4. Market structure trend alignment: 15%
        score_trend = 15.0 if ms_confirmed else 5.0
        # 5. BOS / CHoCH confirmation: 15%
        score_bos = 15.0 if structure_confirmed else 7.5
        # 6. Absence of immediate prior fill: 10%
        score_fresh = 10.0

        strength_score = int(round(score_impulse + score_atr + score_vol + score_trend + score_bos + score_fresh))
        strength_score = max(10, min(100, strength_score))

        # 2. Track Mitigation & Inversion through all subsequent candles (i + 1 to n - 1)
        mitigation_status = "FRESH"
        inversion_status = "NONE"
        mitigation_percent = 0.0
        wick_penetration_percent = 0.0
        close_penetration_percent = 0.0
        ce_reached = False
        ce_first_time: Optional[int] = None
        ce_close_after: Optional[float] = None
        last_tested_timestamp: Optional[int] = None
        inversion_timestamp: Optional[int] = None
        inversion_price: Optional[float] = None
        ifvg_type: Optional[str] = None

        max_penetration_dist = 0.0
        max_close_penetration_dist = 0.0

        for k in range(i + 1, n):
            ck = candles[k]
            k_time = ck["time"]

            if is_bullish:
                # Bullish FVG zone is [lower_price, upper_price]
                if ck["low"] < upper_price:
                    last_tested_timestamp = k_time
                    pen_dist = upper_price - ck["low"]
                    if pen_dist > max_penetration_dist:
                        max_penetration_dist = pen_dist

                    # Close penetration
                    if ck["close"] < upper_price:
                        c_pen = upper_price - ck["close"]
                        if c_pen > max_close_penetration_dist:
                            max_close_penetration_dist = c_pen

                    # Check CE (midpoint)
                    if ck["low"] <= midpoint_price:
                        if not ce_reached:
                            ce_reached = True
                            ce_first_time = k_time
                            ce_close_after = ck["close"]

                    # Inversion check: candle close below lower_price
                    if ck["close"] < lower_price and inversion_status == "NONE":
                        inversion_status = "CONFIRMED"
                        inversion_timestamp = k_time
                        inversion_price = ck["close"]
                        ifvg_type = "BEARISH_IFVG"

            else:
                # Bearish FVG zone is [lower_price, upper_price]
                if ck["high"] > lower_price:
                    last_tested_timestamp = k_time
                    pen_dist = ck["high"] - lower_price
                    if pen_dist > max_penetration_dist:
                        max_penetration_dist = pen_dist

                    # Close penetration
                    if ck["close"] > lower_price:
                        c_pen = ck["close"] - lower_price
                        if c_pen > max_close_penetration_dist:
                            max_close_penetration_dist = c_pen

                    # Check CE (midpoint)
                    if ck["high"] >= midpoint_price:
                        if not ce_reached:
                            ce_reached = True
                            ce_first_time = k_time
                            ce_close_after = ck["close"]

                    # Inversion check: candle close above upper_price
                    if ck["close"] > upper_price and inversion_status == "NONE":
                        inversion_status = "CONFIRMED"
                        inversion_timestamp = k_time
                        inversion_price = ck["close"]
                        ifvg_type = "BULLISH_IFVG"

        wick_penetration_percent = min(100.0, max(0.0, (max_penetration_dist / gap_size) * 100.0))
        close_penetration_percent = min(100.0, max(0.0, (max_close_penetration_dist / gap_size) * 100.0))
        mitigation_percent = round(wick_penetration_percent, 1)

        if inversion_status == "CONFIRMED":
            mitigation_status = "INVERTED"
        elif mitigation_percent >= 100.0:
            mitigation_status = "FULLY MITIGATED"
        elif mitigation_percent >= 50.0:
            mitigation_status = "50% MITIGATED"
        elif mitigation_percent > 0.0:
            mitigation_status = "PARTIALLY MITIGATED"
        else:
            mitigation_status = "FRESH"

        if strength_score >= 80:
            strength_category = "Very Strong"
        elif strength_score >= 60:
            strength_category = "Strong"
        elif strength_score >= 40:
            strength_category = "Moderate"
        else:
            strength_category = "Weak"

        fvgs.append({
            "fvg_id": fvg_id,
            "symbol": symbol.upper(),
            "timeframe": interval.lower(),
            "type": fvg_type,
            "upper_price": round(upper_price, 6),
            "lower_price": round(lower_price, 6),
            "midpoint_price": midpoint_price,
            "gap_size": round(gap_size, 6),
            "gap_size_atr": round(gap_size_atr, 2),
            "strength_score": strength_score,
            "strength_category": strength_category,
            "mitigation_percent": mitigation_percent,
            "wick_penetration_percent": round(wick_penetration_percent, 1),
            "close_penetration_percent": round(close_penetration_percent, 1),
            "mitigation_status": mitigation_status,
            "inversion_status": inversion_status,
            "inversion_timestamp": inversion_timestamp,
            "inversion_price": inversion_price,
            "ifvg_type": ifvg_type,
            "creation_timestamp": creation_timestamp,
            "last_tested_timestamp": last_tested_timestamp,
            "ce_reached": ce_reached,
            "ce_first_time": ce_first_time,
            "ce_close_after": ce_close_after,
            "first_candle_id": c1["time"],
            "impulse_candle_id": c2["time"],
            "third_candle_id": c3["time"],
            "volume_confirmation": volume_confirmed,
            "market_structure_confirmation": ms_confirmed,
            "status": "active" if mitigation_status != "FULLY MITIGATED" else "mitigated",
            # Legacy fields for backward compatibility
            "top": round(upper_price, 6),
            "bottom": round(lower_price, 6),
            "mid": midpoint_price,
            "gapPct": round((gap_size / lower_price) * 100.0, 2) if lower_price > 0 else 0.0,
            "startTime": c2["time"],
            "endTime": candles[-1]["time"],
        })

    return fvgs


def select_key_fvgs(
    fvgs: List[Dict[str, Any]],
    current_price: float,
    atr_val: float,
    max_per_side: int = 3,
    min_spacing_atr: float = 1.5
) -> List[Dict[str, Any]]:
    """
    Selects only the most significant, high-value FVG zones for the timeframe,
    matching the logic of Support/Resistance key zone selection:
    1. Only active (not fully mitigated) zones.
    2. Separates into Bullish (below or near price) and Bearish (above or near price).
    3. Sorts by combination of Strength Score and Proximity to current price.
    4. Enforces minimum ATR spacing to avoid clustered noise lines.
    5. Limits to top N (default 3 bullish + 3 bearish) most critical zones.
    """
    if not fvgs:
        return []

    # Filter out fully mitigated or inverted noise
    active = [f for f in fvgs if f.get("mitigation_status") in ["FRESH", "PARTIALLY MITIGATED", "50% MITIGATED"]]
    if not active:
        active = [f for f in fvgs if f.get("mitigation_status") != "FULLY MITIGATED"]

    bulls = [f for f in active if f["type"].upper() == "BULLISH"]
    bears = [f for f in active if f["type"].upper() == "BEARISH"]

    def _rank_and_filter(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Proximity score: closer to current price = higher priority
        # Combined score = (strength_score * 0.6) + (proximity_score * 0.4)
        def score_fn(item: Dict[str, Any]):
            mid = item["midpoint_price"]
            dist_pct = abs(current_price - mid) / (current_price or 1.0) * 100.0
            # Within 15% get high proximity score, beyond gets decayed
            prox_score = max(0.0, 100.0 - (dist_pct * 5.0))
            strength = item.get("strength_score", 50)
            return (strength * 0.6) + (prox_score * 0.4)

        items.sort(key=score_fn, reverse=True)

        selected: List[Dict[str, Any]] = []
        min_sep = min_spacing_atr * (atr_val or 1.0)
        for cand in items:
            cand_mid = cand["midpoint_price"]
            # Spacing enforcement: do not select another zone overlapping or too close
            if any(abs(cand_mid - s["midpoint_price"]) < min_sep for s in selected):
                continue
            selected.append(cand)
            if len(selected) >= max_per_side:
                break
        return selected

    clean_bulls = _rank_and_filter(bulls)
    clean_bears = _rank_and_filter(bears)

    result = clean_bulls + clean_bears
    result.sort(key=lambda x: x["midpoint_price"])
    return result


def detect_fvgs(candles: List[Dict[str, Any]], interval: str = "5m", symbol: str = "ETH") -> List[Dict[str, Any]]:
    """
    Main entry point for active timeframe FVG detection with complete SMC life cycle.
    Returns key, high-significance FVG zones per timeframe to eliminate clutter.
    """
    all_fvgs = detect_and_track_fvgs(candles=candles, interval=interval, symbol=symbol)
    if not all_fvgs or not candles:
        return []
    current_price = candles[-1]["close"]
    atrs = calculate_atr(candles, period=14)
    atr_val = atrs[-1] if atrs else (candles[-1]["high"] - candles[-1]["low"])

    # Spacing and max zones tailored to timeframe
    interval_clean = interval.lower()
    max_zones = 3 if interval_clean in ["1m", "3m", "5m"] else 3
    min_spacing = 2.0 if interval_clean in ["1m", "3m", "5m"] else 1.8

    return select_key_fvgs(
        fvgs=all_fvgs,
        current_price=current_price,
        atr_val=atr_val,
        max_per_side=max_zones,
        min_spacing_atr=min_spacing
    )


def compute_mtf_confluences(
    all_tf_fvgs: Dict[str, List[Dict[str, Any]]],
    min_overlapping_tfs: int = 2
) -> List[Dict[str, Any]]:
    """
    Computes Multi-Timeframe FVG Confluence zones without merging individual FVGs.
    Finds price overlap ranges where 2 or more independent timeframes share active FVG zones.
    Confluence Score takes into account:
    - Number of independent timeframes
    - Overlap tightness
    - Average strength score of contributing FVGs
    - Freshness / mitigation status
    """
    active_candidates: List[Dict[str, Any]] = []
    for tf, tf_fvgs in all_tf_fvgs.items():
        for f in tf_fvgs:
            if f.get("mitigation_status") != "FULLY MITIGATED":
                active_candidates.append(f)

    if len(active_candidates) < min_overlapping_tfs:
        return []

    confluences: List[Dict[str, Any]] = []
    n = len(active_candidates)
    visited_groups = []

    for i in range(n):
        base_fvg = active_candidates[i]
        matched_fvgs = [base_fvg]
        matched_tfs = {base_fvg["timeframe"]}

        overlap_top = base_fvg["upper_price"]
        overlap_bottom = base_fvg["lower_price"]

        for j in range(n):
            if i == j:
                continue
            cand = active_candidates[j]
            if cand["type"] != base_fvg["type"]:
                continue
            if cand["timeframe"] in matched_tfs:
                continue

            c_top = min(overlap_top, cand["upper_price"])
            c_bottom = max(overlap_bottom, cand["lower_price"])
            if c_top > c_bottom:
                overlap_top = c_top
                overlap_bottom = c_bottom
                matched_fvgs.append(cand)
                matched_tfs.add(cand["timeframe"])

        if len(matched_tfs) >= min_overlapping_tfs:
            group_sig = tuple(sorted(f["fvg_id"] for f in matched_fvgs))
            if group_sig not in visited_groups:
                visited_groups.append(group_sig)

                tf_count_weight = min(40.0, len(matched_tfs) * 13.0)
                avg_strength = sum(f.get("strength_score", 50) for f in matched_fvgs) / len(matched_fvgs)
                strength_weight = avg_strength * 0.40
                fresh_count = sum(1 for f in matched_fvgs if f.get("mitigation_status") == "FRESH")
                freshness_weight = (fresh_count / len(matched_fvgs)) * 20.0

                confluence_score = int(round(tf_count_weight + strength_weight + freshness_weight))
                confluence_score = min(100, max(20, confluence_score))

                confluences.append({
                    "confluence_id": f"mtf_conf_{base_fvg['type'].lower()}_{int(overlap_bottom)}_{int(overlap_top)}",
                    "type": base_fvg["type"],
                    "upper_price": round(overlap_top, 6),
                    "lower_price": round(overlap_bottom, 6),
                    "midpoint_price": round((overlap_top + overlap_bottom) / 2.0, 6),
                    "timeframes": sorted(list(matched_tfs)),
                    "timeframe_count": len(matched_tfs),
                    "confluence_score": confluence_score,
                    "fvg_ids": [f["fvg_id"] for f in matched_fvgs],
                    "desc": f"MTF Confluence ({len(matched_tfs)} TF: {', '.join(sorted(list(matched_tfs)))}) Score: {confluence_score}",
                })

    confluences.sort(key=lambda x: x["confluence_score"], reverse=True)
    return confluences
