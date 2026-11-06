from typing import List, Dict, Any
from .levels import find_pivot_points, cluster_levels

def detect_liquidity_and_sweeps(candles: List[Dict[str, Any]], interval: str = "5m", tolerance_pct: float = 0.25) -> Dict[str, Any]:
    """
    Detects:
    1. Equal Highs (EQH) / Equal Lows (EQL) - Liquidity Pools
    2. Liquidity Sweeps / False Breakouts (Хибні пробої)
    3. Robust Trendlines (Наклонки)
    """
    if len(candles) < 15:
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

    # 2. Liquidity Sweeps (Хибні пробої)
    # Check last 12 candles for sweeps
    sweeps = []
    lookback_candles = candles[-12:]

    # Resistance sweeps (Bearish Sweeps -> Short)
    candidate_highs = [ch["price"] for ch in clustered_highs]
    for level_px in candidate_highs:
        for rc in lookback_candles:
            if rc["high"] > level_px and rc["close"] < level_px:
                wick_pct = (rc["high"] - level_px) / level_px * 100
                if wick_pct >= 0.04:
                    sweeps.append({
                        "type": "bearish_sweep",
                        "formation": "Хибний пробій опору",
                        "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                        "sweepPrice": round(rc["high"], 2 if rc["high"] > 10 else 4),
                        "direction": "SHORT",
                        "time": rc["time"],
                        "desc": f"Хибний пробій опору {level_px:.2f}, виніс стопів тінню свічки та повернення під рівень"
                    })

    # Support sweeps (Bullish Sweeps -> Long)
    candidate_lows = [cl["price"] for cl in clustered_lows]
    for level_px in candidate_lows:
        for rc in lookback_candles:
            if rc["low"] < level_px and rc["close"] > level_px:
                wick_pct = (level_px - rc["low"]) / level_px * 100
                if wick_pct >= 0.04:
                    sweeps.append({
                        "type": "bullish_sweep",
                        "formation": "Хибний пробій підтримки",
                        "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                        "sweepPrice": round(rc["low"], 2 if rc["low"] > 10 else 4),
                        "direction": "LONG",
                        "time": rc["time"],
                        "desc": f"Хибний пробій підтримки {level_px:.2f}, виніс стопів тінню свічки та відкуп"
                    })

    # Merge / Deduplicate nearby sweeps so we NEVER spam overlapping lines
    clean_sweeps = []
    seen_levels = []
    for s in sweeps:
        # Check if already have a sweep within 0.3% price
        is_duplicate = False
        for sl in seen_levels:
            if abs(s["levelPrice"] - sl) / sl * 100 < 0.3:
                is_duplicate = True
                break
        if not is_duplicate:
            seen_levels.append(s["levelPrice"])
            clean_sweeps.append(s)

    # Keep at most 2 closest clean sweeps to guarantee pristine chart readability
    clean_sweeps = clean_sweeps[:2]

    # 3. Robust Trendlines (Наклонки)
    trendlines = []
    if len(highs) >= 2:
        recent_h = highs[-5:]
        best_res_tl = None
        best_diff = 0
        for i in range(len(recent_h) - 1):
            for j in range(i + 1, len(recent_h)):
                h1, h2 = recent_h[i], recent_h[j]
                if h1["price"] > h2["price"]:
                    diff = h1["price"] - h2["price"]
                    if diff > best_diff:
                        best_diff = diff
                        best_res_tl = {
                            "type": "resistance_trendline",
                            "label": "Наклонка (Опір)",
                            "p1": {"time": h1["time"], "price": round(h1["price"], 2 if h1["price"] > 10 else 4)},
                            "p2": {"time": h2["time"], "price": round(h2["price"], 2 if h2["price"] > 10 else 4)}
                        }
        if best_res_tl:
            trendlines.append(best_res_tl)

    if len(lows) >= 2:
        recent_l = lows[-5:]
        best_sup_tl = None
        best_diff = 0
        for i in range(len(recent_l) - 1):
            for j in range(i + 1, len(recent_l)):
                l1, l2 = recent_l[i], recent_l[j]
                if l2["price"] > l1["price"]:
                    diff = l2["price"] - l1["price"]
                    if diff > best_diff:
                        best_diff = diff
                        best_sup_tl = {
                            "type": "support_trendline",
                            "label": "Наклонка (Підтримка)",
                            "p1": {"time": l1["time"], "price": round(l1["price"], 2 if l1["price"] > 10 else 4)},
                            "p2": {"time": l2["time"], "price": round(l2["price"], 2 if l2["price"] > 10 else 4)}
                        }
        if best_sup_tl:
            trendlines.append(best_sup_tl)

    return {
        "pools": pools[-4:],
        "sweeps": clean_sweeps,
        "trendlines": trendlines
    }
