import asyncio
import sys
import os
import math
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    find_swings_for_trendlines,
    calculate_atr,
)

def evaluate_adaptive_quality(candles, tl, atr):
    """
    New Multi-Factor Adaptive Quality Model (0 - 100):
    1. Touch Quality & Distribution (25 pts)
    2. Reaction Strength (20 pts)
    3. Pivot Significance (15 pts)
    4. Geometric Accuracy & Slope (15 pts)
    5. Trend Consistency (10 pts)
    6. Recency (15 pts)
    7. Penalties (Broken -35, Stale -20)
    """
    idx1 = tl["start_point"]["index"]
    idx2 = tl["end_point"]["index"]
    price1 = tl["start_point"]["price"]
    price2 = tl["end_point"]["price"]
    slope = tl["slope"]
    abs_slope = abs(slope)
    is_res = tl["line_type"] == "resistance_trendline"
    n_candles = len(candles)
    bar_dist = idx2 - idx1

    # 1. Touch Quality (max 25 pts)
    # Collect all touch indices and their closeness
    touches = [idx1, idx2]
    touch_distances = [] # in ATR
    for k in range(idx1 + 1, n_candles):
        if k == idx2 or k in touches:
            continue
        line_p = price1 + slope * (k - idx1)
        c_k = candles[k]
        if is_res:
            dist = line_p - c_k["high"]
            if -0.25 * atr <= dist <= 0.35 * atr:
                touches.append(k)
                touch_distances.append(abs(dist) / atr)
        else:
            dist = c_k["low"] - line_p
            if -0.25 * atr <= dist <= 0.35 * atr:
                touches.append(k)
                touch_distances.append(abs(dist) / atr)

    touches.sort()
    n_touches = len(touches)

    # Count score: 3-4 touches is optimal peak (15 pts), 2 touches (8 pts), 5+ touches (12 pts due to exhaustion)
    if n_touches == 2:
        touch_count_pts = 8.0
    elif n_touches == 3:
        touch_count_pts = 16.0
    elif n_touches == 4:
        touch_count_pts = 15.0
    elif n_touches == 5:
        touch_count_pts = 12.0
    else:
        touch_count_pts = 9.0

    # Touch spacing uniformity (max 5 pts)
    if n_touches >= 3:
        intervals = [touches[i] - touches[i-1] for i in range(1, len(touches))]
        mean_int = sum(intervals) / len(intervals)
        var = sum((x - mean_int)**2 for x in intervals) / len(intervals)
        std_int = math.sqrt(var)
        cv = std_int / max(mean_int, 1.0)
        # Low cv = uniform spacing
        spacing_pts = max(0.0, 5.0 * (1.0 - min(cv, 1.0)))
    else:
        spacing_pts = 3.0

    # Touch precision (max 4 pts): how close to the line (average distance in ATR)
    avg_touch_dist = (sum(touch_distances) / len(touch_distances)) if touch_distances else 0.1
    precision_pts = max(0.0, 4.0 * (1.0 - min(avg_touch_dist / 0.35, 1.0)))

    touch_quality_score = min(25.0, touch_count_pts + spacing_pts + precision_pts)

    # 2. Reaction Strength (max 20 pts)
    # Measure post-touch bounce amplitude for historical touches (excluding last uncompleted bar)
    bounces_atr = []
    for t_idx in touches:
        if t_idx >= n_candles - 3:
            continue
        t_line_p = price1 + slope * (t_idx - idx1)
        max_bounce = 0.0
        for f in range(1, min(12, n_candles - t_idx)):
            c_f = candles[t_idx + f]
            if is_res:
                bounce = t_line_p - c_f["low"]
            else:
                bounce = c_f["high"] - t_line_p
            if bounce > max_bounce:
                max_bounce = bounce
        bounces_atr.append(max_bounce / atr)

    avg_bounce_atr = (sum(bounces_atr) / len(bounces_atr)) if bounces_atr else 1.5
    # 2.5+ ATR bounce = 20 pts, 1.5 ATR = 14 pts, 0.5 ATR = 5 pts
    reaction_score = min(20.0, max(2.0, (avg_bounce_atr / 2.5) * 20.0))

    # 3. Pivot Significance (max 15 pts)
    # Check swing prominence of p1 and p2 in ATR
    # Prominence: drop/rise relative to surrounding 5 bars
    c1 = candles[idx1]
    c2 = candles[idx2]
    if is_res:
        prom1 = (c1["high"] - min(candles[max(0, idx1-5)]["low"], candles[min(n_candles-1, idx1+5)]["low"])) / atr
        prom2 = (c2["high"] - min(candles[max(0, idx2-5)]["low"], candles[min(n_candles-1, idx2+5)]["low"])) / atr
    else:
        prom1 = (max(candles[max(0, idx1-5)]["high"], candles[min(n_candles-1, idx1+5)]["high"]) - c1["low"]) / atr
        prom2 = (max(candles[max(0, idx2-5)]["high"], candles[min(n_candles-1, idx2+5)]["high"]) - c2["low"]) / atr

    avg_prom = (prom1 + prom2) / 2.0
    pivot_score = min(15.0, max(3.0, (avg_prom / 3.0) * 15.0))

    # 4. Geometric Accuracy & Slope (max 15 pts)
    # Optimal slope: 0.1 to 0.7 ATR per bar
    if 0.1 * atr <= abs_slope <= 0.6 * atr:
        slope_pts = 10.0
    elif 0.05 * atr <= abs_slope <= 0.9 * atr:
        slope_pts = 6.0
    else:
        slope_pts = 2.0

    # Span bonus (15 to 80 bars is healthy)
    if 12 <= bar_dist <= 75:
        span_pts = 5.0
    elif bar_dist > 75:
        span_pts = 3.0
    else:
        span_pts = 2.0

    geometry_score = slope_pts + span_pts

    # 5. Trend Consistency (max 10 pts)
    # Compare against 50-period SMA direction
    sma_period = min(50, n_candles)
    recent_closes = [c["close"] for c in candles[-sma_period:]]
    sma = sum(recent_closes) / len(recent_closes)
    current_p = candles[-1]["close"]
    if (is_res and current_p < sma) or (not is_res and current_p > sma):
        trend_consistency_score = 10.0
    else:
        trend_consistency_score = 5.0

    # 6. Recency (max 15 pts)
    last_touch_idx = touches[-1]
    bars_since_last_touch = n_candles - 1 - last_touch_idx
    if bars_since_last_touch <= 8:
        recency_score = 15.0
    elif bars_since_last_touch <= 20:
        recency_score = 10.0
    elif bars_since_last_touch <= 40:
        recency_score = 6.0
    else:
        recency_score = 2.0

    # Total Base Score (max 100)
    raw_total = (
        touch_quality_score +
        reaction_score +
        pivot_score +
        geometry_score +
        trend_consistency_score +
        recency_score
    )

    # 7. Status & Breakout Integrity Penalties
    status = tl["status"]
    if status == "BROKEN":
        final_score = max(5.0, raw_total - 35.0)
    elif status == "STALE":
        final_score = max(10.0, raw_total - 20.0)
    else:
        final_score = min(98.0, raw_total) # 100 requires near-perfection across all 6 metrics!

    # Categorization based on empirical quantiles
    if final_score >= 82.0:
        category = "EXCELLENT"
    elif final_score >= 68.0:
        category = "STRONG"
    elif final_score >= 50.0:
        category = "MODERATE"
    else:
        category = "WEAK"

    return {
        "score": round(final_score, 1),
        "category": category,
        "components": {
            "touch_quality": round(touch_quality_score, 1),
            "reaction_strength": round(reaction_score, 1),
            "pivot_significance": round(pivot_score, 1),
            "geometric_accuracy": round(geometry_score, 1),
            "trend_consistency": round(trend_consistency_score, 1),
            "recency": round(recency_score, 1),
        },
        "touches": n_touches,
        "avg_bounce_atr": round(avg_bounce_atr, 2),
    }

async def run_simulation():
    from app.analyzer.trendline import detect_timeframe_trendlines
    coins = ["BTC", "ETH", "SOL", "PUMP", "MET"]
    tfs = ["5m", "15m", "1h", "4h", "1d"]

    histogram_new = defaultdict(int)
    cat_counts = defaultdict(int)
    all_scores = []

    print("Evaluating new Adaptive Quality Model on real market data...")
    for coin in coins:
        for tf in tfs:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=400)
            if not candles or len(candles) < 30:
                continue
            atr = calculate_atr(candles, period=14)
            tls = detect_timeframe_trendlines(candles, interval=tf, include_broken=True, max_lines_per_type=3)
            for tl in tls:
                eval_res = evaluate_adaptive_quality(candles, tl, atr)
                sc = eval_res["score"]
                cat = eval_res["category"]
                all_scores.append(sc)
                bucket = int(sc // 10) * 10
                histogram_new[bucket] += 1
                cat_counts[cat] += 1

    await hl_client.close()

    total = len(all_scores)
    print("\n" + "=" * 80)
    print(f"📊 NEW SCORE DISTRIBUTION (Total lines = {total})")
    print("=" * 80)
    for b in sorted(histogram_new.keys()):
        cnt = histogram_new[b]
        pct = cnt / total * 100
        bar = "█" * int(pct // 2)
        print(f"  Score {b:2d} - {b+9:2d}: {cnt:3d} lines ({pct:5.1f}%) {bar}")

    print("\n" + "=" * 80)
    print("🏷️ QUALITY CATEGORIES")
    print("=" * 80)
    for cat in ["EXCELLENT", "STRONG", "MODERATE", "WEAK"]:
        cnt = cat_counts[cat]
        pct = cnt / total * 100
        print(f"  • {cat:10s}: {cnt:3d} lines ({pct:5.1f}%)")

if __name__ == "__main__":
    asyncio.run(run_simulation())
