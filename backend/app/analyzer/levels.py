from typing import List, Dict, Any

INTERVAL_CONFIG = {
    "1m": {"left": 4, "right": 4, "tol": 0.18, "min_thickness": 0.0010, "max_levels": 3},
    "3m": {"left": 4, "right": 4, "tol": 0.22, "min_thickness": 0.0012, "max_levels": 3},
    "5m": {"left": 4, "right": 4, "tol": 0.25, "min_thickness": 0.0015, "max_levels": 3},
    "15m": {"left": 3, "right": 3, "tol": 0.35, "min_thickness": 0.0020, "max_levels": 3},
    "30m": {"left": 3, "right": 3, "tol": 0.45, "min_thickness": 0.0025, "max_levels": 3},
    "1h": {"left": 3, "right": 3, "tol": 0.55, "min_thickness": 0.0030, "max_levels": 3},
    "2h": {"left": 3, "right": 3, "tol": 0.70, "min_thickness": 0.0040, "max_levels": 3},
    "4h": {"left": 3, "right": 3, "tol": 0.85, "min_thickness": 0.0050, "max_levels": 3},
    "1d": {"left": 3, "right": 3, "tol": 1.20, "min_thickness": 0.0080, "max_levels": 3},
}

def find_pivot_points(candles: List[Dict[str, Any]], left_bars: int = 3, right_bars: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """
    Finds swing highs and swing lows using rolling fractals for the active timeframe.
    """
    if len(candles) < (left_bars + right_bars + 1):
        return {"highs": [], "lows": []}

    highs = []
    lows = []
    n = len(candles)

    for i in range(left_bars, n - right_bars):
        curr_high = candles[i]["high"]
        curr_low = candles[i]["low"]
        time_sec = candles[i]["time"]

        # Pivot High
        is_high = True
        for offset in range(-left_bars, right_bars + 1):
            if offset != 0 and candles[i + offset]["high"] >= curr_high:
                is_high = False
                break
        if is_high:
            highs.append({"price": curr_high, "time": time_sec, "index": i})

        # Pivot Low
        is_low = True
        for offset in range(-left_bars, right_bars + 1):
            if offset != 0 and candles[i + offset]["low"] <= curr_low:
                is_low = False
                break
        if is_low:
            lows.append({"price": curr_low, "time": time_sec, "index": i})

    return {"highs": highs, "lows": lows}


def cluster_levels(
    points: List[Dict[str, Any]],
    current_price: float,
    tolerance_pct: float = 0.3,
    min_thickness_ratio: float = 0.0015
) -> List[Dict[str, Any]]:
    """
    Clusters nearby swings into consolidated, high-significance PRICE ZONES.
    Filters out insignificant 1-touch noise when stronger levels exist.
    """
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

        # Minimum realistic zone thickness based on timeframe
        min_thickness = avg_price * min_thickness_ratio
        if (max_p - min_p) < min_thickness:
            top = avg_price + (min_thickness / 2)
            bottom = avg_price - (min_thickness / 2)
        else:
            top = max_p
            bottom = min_p

        # Distance calculation
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
            "strength": min(touches, 5)
        })

    return result


def analyze_levels(candles: List[Dict[str, Any]], interval: str = "5m") -> Dict[str, Any]:
    """
    Analyzes candlestick data STRICTLY for the active timeframe.
    Limits output to the TOP 2-3 most important, closest key zones to eliminate clutter.
    """
    if not candles:
        return {"resistances": [], "supports": [], "cascades": []}

    clean_interval = interval.lower()
    cfg = INTERVAL_CONFIG.get(clean_interval, INTERVAL_CONFIG["5m"])

    current_price = candles[-1]["close"]
    pivots = find_pivot_points(candles, left_bars=cfg["left"], right_bars=cfg["right"])

    clustered_highs = cluster_levels(
        pivots["highs"], current_price, tolerance_pct=cfg["tol"], min_thickness_ratio=cfg["min_thickness"]
    )
    clustered_lows = cluster_levels(
        pivots["lows"], current_price, tolerance_pct=cfg["tol"], min_thickness_ratio=cfg["min_thickness"]
    )

    # Resistances: zones above current price
    resistances = [l for l in clustered_highs if l["bottom"] >= current_price or l["price"] >= current_price]
    # Supports: zones below current price
    supports = [l for l in clustered_lows if l["top"] <= current_price or l["price"] <= current_price]

    # Sort Resistances ascending (closest first)
    resistances.sort(key=lambda x: x["bottom"])
    # Sort Supports descending (closest first)
    supports.sort(key=lambda x: x["top"], reverse=True)

    # PRIORITIZE:
    # If we have tested levels (touches >= 2), filter out weak 1-touch noise that is far away
    max_count = cfg["max_levels"] # max 3 levels each

    # Only keep the closest max_count resistances and supports
    clean_resistances = resistances[:max_count]
    clean_supports = supports[:max_count]

    # Detect Cascades within the closest clean levels
    cascades = []
    if len(clean_resistances) >= 2:
        r1, r2 = clean_resistances[0], clean_resistances[1]
        diff = (r2["price"] - r1["price"]) / r1["price"] * 100
        if diff < 2.5 and r1["touches"] >= 2:
            cascades.append({
                "type": "resistance_cascade",
                "levels": [r1["price"], r2["price"]],
                "desc": f"Каскад зон опору ({r1['price']}, {r2['price']})",
                "distPct": r1["distPct"]
            })

    return {
        "currentPrice": current_price,
        "resistances": clean_resistances,
        "supports": clean_supports,
        "cascades": cascades
    }
