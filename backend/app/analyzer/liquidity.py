from typing import List, Dict, Any, Optional
from .levels import find_pivot_points, cluster_levels
from .false_breakout import detect_false_breakouts

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
