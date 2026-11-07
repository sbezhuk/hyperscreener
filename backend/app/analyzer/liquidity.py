from typing import List, Dict, Any, Optional
from .levels import find_pivot_points, cluster_levels, _calculate_atr
from .false_breakout import detect_false_breakouts
from .trendline import detect_timeframe_trendlines


def _find_best_trendline(
    candles: List[Dict[str, Any]],
    pivots: List[Dict[str, Any]],
    tl_type: str,
    atr: float,
) -> Optional[Dict[str, Any]]:
    """
    Selects high-quality, actionable trendlines with:
    1. Minimum bar spacing (eliminates micro-chop).
    2. Slope steepness limits (eliminates vertical crash/pump lines).
    3. Geometrical validity (candle bodies do not penetrate the line between anchors).
    4. Invalidation check (excludes lines already broken by current price or recent closes).
    5. Scoring based on touches, healthy slope, and bar span.
    """
    if len(pivots) < 2 or not candles:
        return None

    if atr <= 0:
        atr = max(candles[-1].get("close", 1.0) * 0.01, 0.0001)

    n_candles = len(candles)
    recent_p = pivots[-8:] if len(pivots) >= 8 else pivots
    best_candidate = None
    best_score = -1.0

    is_res = (tl_type == "resistance_trendline")

    for i in range(len(recent_p) - 1):
        for j in range(i + 1, len(recent_p)):
            p1, p2 = recent_p[i], recent_p[j]
            idx1 = p1.get("index")
            idx2 = p2.get("index")
            if idx1 is None or idx2 is None or idx2 <= idx1:
                continue

            bar_dist = idx2 - idx1
            # 1. Require at least 4 bars separation to avoid micro-noise
            if bar_dist < 4:
                continue

            price1 = p1["price"]
            price2 = p2["price"]

            # 2. Check direction & calculate slope
            if is_res:
                if price1 <= price2:
                    continue
                diff = price1 - price2
                slope = (price2 - price1) / bar_dist
            else:
                if price2 <= price1:
                    continue
                diff = price2 - price1
                slope = (price2 - price1) / bar_dist

            abs_slope = abs(slope)

            # 3. Slope magnitude checks
            # Must have noticeable slope (not completely flat like a horizontal level)
            if diff < 0.4 * atr or abs_slope < 0.02 * atr:
                continue
            # Must not be an absurd vertical cliff (> 1.6 ATR per bar continuously)
            if abs_slope > 1.6 * atr:
                continue

            # 4. Geometrical validity between idx1 and idx2
            # No candle body should penetrate significantly across the line
            penetrated = False
            for k in range(idx1 + 1, idx2):
                c_k = candles[k]
                line_p = price1 + slope * (k - idx1)
                if is_res:
                    if c_k["close"] > line_p + 0.25 * atr or c_k["high"] > line_p + 0.6 * atr:
                        penetrated = True
                        break
                else:
                    if c_k["close"] < line_p - 0.25 * atr or c_k["low"] < line_p - 0.6 * atr:
                        penetrated = True
                        break

            if penetrated:
                continue

            # 5. Invalidation after idx2 (must be active, not broken)
            curr_c = candles[-1]
            latest_line_p = price1 + slope * (n_candles - 1 - idx1)
            if is_res:
                if curr_c["close"] > latest_line_p + 0.2 * atr:
                    # Current price is above resistance -> broken!
                    continue
            else:
                if curr_c["close"] < latest_line_p - 0.2 * atr:
                    # Current price is below support -> broken!
                    continue

            # Check if multiple candles after idx2 closed on the wrong side
            break_count = 0
            for k in range(idx2 + 1, n_candles):
                c_k = candles[k]
                line_p = price1 + slope * (k - idx1)
                if is_res and c_k["close"] > line_p + 0.25 * atr:
                    break_count += 1
                elif not is_res and c_k["close"] < line_p - 0.25 * atr:
                    break_count += 1

            if break_count >= 2:
                # Confirmed broken after pivot 2
                continue

            # 6. Quality Scoring
            score = 50.0
            # Additional touches bonus
            touch_count = 2
            for k in range(idx1 + 1, n_candles):
                c_k = candles[k]
                line_p = price1 + slope * (k - idx1)
                if is_res:
                    if abs(c_k["high"] - line_p) <= 0.3 * atr:
                        touch_count += 1
                else:
                    if abs(c_k["low"] - line_p) <= 0.3 * atr:
                        touch_count += 1

            score += min((touch_count - 2) * 12.0, 36.0)

            # Healthy span bonus
            if 6 <= bar_dist <= 60:
                score += 15.0
            elif bar_dist > 60:
                score += 5.0

            # Healthy angle / slope bonus (0.08 to 0.8 ATR/bar)
            if 0.08 * atr <= abs_slope <= 0.8 * atr:
                score += 15.0

            # Recency bonus (pivot 2 is relatively fresh)
            bars_since_p2 = n_candles - 1 - idx2
            if bars_since_p2 <= 15:
                score += 10.0

            if score > best_score:
                best_score = score
                best_candidate = {
                    "type": tl_type,
                    "label": "Наклонка (Опір)" if is_res else "Наклонка (Підтримка)",
                    "p1": {"time": p1["time"], "price": round(price1, 2 if price1 > 10 else 4)},
                    "p2": {"time": p2["time"], "price": round(price2, 2 if price2 > 10 else 4)},
                    "score": round(score, 1),
                    "touches": touch_count,
                }

    return best_candidate

def detect_liquidity_and_sweeps(
    candles: List[Dict[str, Any]],
    interval: str = "5m",
    tolerance_pct: float = 0.25,
    levels: Optional[List[Dict[str, Any]]] = None,
    oi_tracker: Optional[Any] = None,
    oi_snapshots: Optional[List[Any]] = None,
    coin: Optional[str] = None,
    oi_config: Optional[Any] = None,
    min_oi_drop_pct: Optional[float] = None,
    only_confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Detects:
    1. Equal Highs (EQH) / Equal Lows (EQL) - Liquidity Pools
    2. Liquidity Sweeps / False Breakouts (Хибні пробої)
    3. Robust Trendlines (Наклонки)
    """
    if len(candles) < 5:
        return {"pools": [], "sweeps": [], "trendlines": []}

    current_price = candles[-1]["close"]
    pivots = find_pivot_points(candles, left_bars=3, right_bars=3)
    highs = pivots["highs"]
    lows = pivots["lows"]

    clustered_highs = cluster_levels(highs, current_price, tolerance_pct)
    clustered_lows = cluster_levels(lows, current_price, tolerance_pct)

    pools = []
    for ch in clustered_highs:
        if ch["touches"] >= 2:
            pools.append({
                "type": "BSL",
                "label": f"Buy-side Liquidity (x{ch['touches']})",
                "price": ch["price"],
                "touches": ch["touches"]
            })

    for cl in clustered_lows:
        if cl["touches"] >= 2:
            pools.append({
                "type": "SSL",
                "label": f"Sell-side Liquidity (x{cl['touches']})",
                "price": cl["price"],
                "touches": cl["touches"]
            })

    # Prepare levels for false breakout detection:
    # Combine provided confirmed levels (from levels engine) with clustered swing levels
    eval_levels: List[Dict[str, Any]] = []
    if levels:
        for lvl in levels:
            eval_levels.append(lvl)
    else:
        for ch in clustered_highs:
            eval_levels.append({
                "price": ch["price"],
                "type": "resistance",
                "touches": ch.get("touches", 1),
                "strength_score": 60.0
            })
        for cl in clustered_lows:
            eval_levels.append({
                "price": cl["price"],
                "type": "support",
                "touches": cl.get("touches", 1),
                "strength_score": 60.0
            })

    # 2. Advanced False Breakouts Detection (covers wick sweeps & multi-candle breakouts with returns & OI drop)
    clean_sweeps = detect_false_breakouts(
        candles=candles,
        levels=eval_levels,
        interval=interval,
        min_touches=1,
        oi_tracker=oi_tracker,
        oi_snapshots=oi_snapshots,
        coin=coin,
        config=oi_config,
        min_oi_drop_pct=min_oi_drop_pct,
        only_confirmed=only_confirmed,
    )

    # 3. Robust Trendlines (Наклонки) independently detected for this timeframe
    trendlines = detect_timeframe_trendlines(candles, interval=interval, include_broken=False)

    return {
        "pools": pools[-4:],
        "sweeps": clean_sweeps,
        "trendlines": trendlines
    }
