import asyncio
import sys
import os
import math
from collections import defaultdict

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    find_swings_for_trendlines,
    calculate_atr,
    TIMEFRAME_SWING_CONFIG,
)

HORIZON = 15  # Forward evaluation horizon in bars
TRAIN_RATIO = 0.65  # 65% In-Sample, 35% Out-of-Sample
COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
TIMEFRAMES = ["15m", "1h"]

def calculate_pit_trendlines(candles_up_to_t, interval, atr):
    """
    Point-in-time trendline detector strictly using only candles up to T.
    Ensures that any swing point at index i was confirmed by right_bars <= T.
    """
    n = len(candles_up_to_t)
    if n < 15:
        return []

    clean_tf = interval.lower()
    config = TIMEFRAME_SWING_CONFIG.get(clean_tf, {"left": 3, "right": 3, "prominence": 0.35})
    left_bars = config["left"]
    right_bars = config["right"]
    min_prominence_atr = config["prominence"]

    # Maximum index for a swing high/low that is fully confirmed at n-1
    max_confirmed_idx = n - 1 - right_bars
    if max_confirmed_idx < left_bars:
        return []

    # Find confirmed swings point-in-time
    highs = []
    lows = []
    for i in range(left_bars, max_confirmed_idx + 1):
        c = candles_up_to_t[i]
        curr_h = c["high"]
        curr_l = c["low"]

        is_h = all(candles_up_to_t[i - k]["high"] < curr_h for k in range(1, left_bars + 1)) and \
               all(candles_up_to_t[i + k]["high"] < curr_h for k in range(1, right_bars + 1))
        if is_h:
            drop_left = curr_h - min(candles_up_to_t[i - k]["low"] for k in range(1, left_bars + 1))
            drop_right = curr_h - min(candles_up_to_t[i + k]["low"] for k in range(1, right_bars + 1))
            if min(drop_left, drop_right) >= min_prominence_atr * atr:
                highs.append({"price": curr_h, "time": c["time"], "index": i})

        is_l = all(candles_up_to_t[i - k]["low"] > curr_l for k in range(1, left_bars + 1)) and \
               all(candles_up_to_t[i + k]["low"] > curr_l for k in range(1, right_bars + 1))
        if is_l:
            rise_left = max(candles_up_to_t[i - k]["high"] for k in range(1, left_bars + 1)) - curr_l
            rise_right = max(candles_up_to_t[i + k]["high"] for k in range(1, right_bars + 1)) - curr_l
            if min(rise_left, rise_right) >= min_prominence_atr * atr:
                lows.append({"price": curr_l, "time": c["time"], "index": i})

    # Build active candidate lines
    active_lines = []

    # Resistance candidates
    recent_highs = highs[-6:] if len(highs) >= 6 else highs
    for i in range(len(recent_highs) - 1):
        for j in range(i + 1, len(recent_highs)):
            p1, p2 = recent_highs[i], recent_highs[j]
            idx1, idx2 = p1["index"], p2["index"]
            bar_dist = idx2 - idx1
            if bar_dist < 4 or p1["price"] <= p2["price"]:
                continue

            # Slope
            slope = (p2["price"] - p1["price"]) / bar_dist
            diff = p1["price"] - p2["price"]
            abs_slope = abs(slope)
            if diff < 0.35 * atr or abs_slope < 0.02 * atr or abs_slope > 1.6 * atr:
                continue

            # Geometrical validity between idx1 and idx2
            penetrated = False
            for k in range(idx1 + 1, idx2):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] > line_p + 0.25 * atr or c_k["high"] > line_p + 0.6 * atr:
                    penetrated = True
                    break
            if penetrated:
                continue

            # Invalidation up to current bar n-1
            break_count = 0
            for k in range(idx2 + 1, n):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] > line_p + 0.25 * atr:
                    break_count += 1
            if break_count >= 2:
                continue

            active_lines.append({
                "type": "resistance_trendline",
                "p1": p1,
                "p2": p2,
                "slope": slope,
                "born_idx": idx2 + right_bars,
            })

    # Support candidates
    recent_lows = lows[-6:] if len(lows) >= 6 else lows
    for i in range(len(recent_lows) - 1):
        for j in range(i + 1, len(recent_lows)):
            p1, p2 = recent_lows[i], recent_lows[j]
            idx1, idx2 = p1["index"], p2["index"]
            bar_dist = idx2 - idx1
            if bar_dist < 4 or p2["price"] <= p1["price"]:
                continue

            slope = (p2["price"] - p1["price"]) / bar_dist
            diff = p2["price"] - p1["price"]
            abs_slope = abs(slope)
            if diff < 0.35 * atr or abs_slope < 0.02 * atr or abs_slope > 1.6 * atr:
                continue

            penetrated = False
            for k in range(idx1 + 1, idx2):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] < line_p - 0.25 * atr or c_k["low"] < line_p - 0.6 * atr:
                    penetrated = True
                    break
            if penetrated:
                continue

            break_count = 0
            for k in range(idx2 + 1, n):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] < line_p - 0.25 * atr:
                    break_count += 1
            if break_count >= 2:
                continue

            active_lines.append({
                "type": "support_trendline",
                "p1": p1,
                "p2": p2,
                "slope": slope,
                "born_idx": idx2 + right_bars,
            })

    return active_lines

def compute_pit_score(candles_up_to_t, line, atr, include_sma=True):
    """
    Computes Adaptive Quality Score (0 - 100) using ONLY information available at bar T.
    """
    idx1 = line["p1"]["index"]
    idx2 = line["p2"]["index"]
    p1_p = line["p1"]["price"]
    slope = line["slope"]
    abs_slope = abs(slope)
    is_res = line["type"] == "resistance_trendline"
    n = len(candles_up_to_t)
    curr_idx = n - 1

    # 1. Historical touches up to curr_idx (anchors p1, p2 are touches 1 and 2)
    touches = [idx1, idx2]
    touch_dists = []
    for k in range(idx1 + 1, curr_idx + 1):
        if k == idx2:
            continue
        line_p = p1_p + slope * (k - idx1)
        c_k = candles_up_to_t[k]
        if is_res:
            dist = line_p - c_k["high"]
            if -0.25 * atr <= dist <= 0.35 * atr:
                touches.append(k)
                touch_dists.append(abs(dist) / atr)
        else:
            dist = c_k["low"] - line_p
            if -0.25 * atr <= dist <= 0.35 * atr:
                touches.append(k)
                touch_dists.append(abs(dist) / atr)

    touches.sort()
    n_touches = len(touches)

    # Touch count factor (raw point-in-time)
    if n_touches == 2:
        touch_pts = 10.0
    elif n_touches == 3:
        touch_pts = 16.0
    elif n_touches == 4:
        touch_pts = 14.0
    else:
        touch_pts = 10.0

    # Spacing uniformity
    if n_touches >= 3:
        intervals = [touches[i] - touches[i-1] for i in range(1, len(touches))]
        mean_int = sum(intervals) / len(intervals)
        var = sum((x - mean_int)**2 for x in intervals) / len(intervals)
        cv = math.sqrt(var) / max(mean_int, 1.0)
        spacing_pts = max(0.0, 5.0 * (1.0 - min(cv, 1.0)))
    else:
        spacing_pts = 3.0

    avg_dist = (sum(touch_dists) / len(touch_dists)) if touch_dists else 0.1
    precision_pts = max(0.0, 4.0 * (1.0 - min(avg_dist / 0.35, 1.0)))
    touch_quality_score = min(25.0, touch_pts + spacing_pts + precision_pts)

    # 2. Historical reaction strength (bounces before curr_idx)
    bounces = []
    for t_idx in touches:
        if t_idx >= curr_idx - 2:
            continue
        t_line = p1_p + slope * (t_idx - idx1)
        max_b = 0.0
        for f in range(1, min(10, curr_idx - t_idx + 1)):
            c_f = candles_up_to_t[t_idx + f]
            b = (t_line - c_f["low"]) if is_res else (c_f["high"] - t_line)
            if b > max_b:
                max_b = b
        bounces.append(max_b / atr)

    avg_b = (sum(bounces) / len(bounces)) if bounces else 1.5
    reaction_score = min(20.0, max(2.0, (avg_b / 2.5) * 20.0))

    # 3. Pivot significance
    c1, c2 = candles_up_to_t[idx1], candles_up_to_t[idx2]
    if is_res:
        prom1 = (c1["high"] - min(candles_up_to_t[max(0, idx1-4)]["low"], candles_up_to_t[min(n-1, idx1+4)]["low"])) / atr
        prom2 = (c2["high"] - min(candles_up_to_t[max(0, idx2-4)]["low"], candles_up_to_t[min(n-1, idx2+4)]["low"])) / atr
    else:
        prom1 = (max(candles_up_to_t[max(0, idx1-4)]["high"], candles_up_to_t[min(n-1, idx1+4)]["high"]) - c1["low"]) / atr
        prom2 = (max(candles_up_to_t[max(0, idx2-4)]["high"], candles_up_to_t[min(n-1, idx2+4)]["high"]) - c2["low"]) / atr
    pivot_score = min(15.0, max(3.0, ((prom1 + prom2) / 2.0 / 3.0) * 15.0))

    # 4. Geometric accuracy & slope
    bar_dist = idx2 - idx1
    slope_pts = 10.0 if (0.1 * atr <= abs_slope <= 0.6 * atr) else (6.0 if 0.05 * atr <= abs_slope <= 0.9 * atr else 2.0)
    span_pts = 5.0 if (12 <= bar_dist <= 75) else (3.0 if bar_dist > 75 else 2.0)
    geometry_score = slope_pts + span_pts

    # 5. Trend consistency (SMA-50)
    if include_sma:
        sma_len = min(50, n)
        sma = sum(c["close"] for c in candles_up_to_t[-sma_len:]) / sma_len
        curr_p = candles_up_to_t[-1]["close"]
        trend_score = 10.0 if ((is_res and curr_p < sma) or (not is_res and curr_p > sma)) else 5.0
    else:
        trend_score = 7.5  # neutral midpoint when SMA is ablated

    # 6. Recency
    last_touch = touches[-1]
    bars_since_last = curr_idx - last_touch
    recency_score = 15.0 if bars_since_last <= 8 else (10.0 if bars_since_last <= 20 else (6.0 if bars_since_last <= 40 else 2.0))

    total = touch_quality_score + reaction_score + pivot_score + geometry_score + trend_score + recency_score
    final_score = min(98.0, max(10.0, total))

    if final_score >= 82.0:
        cat = "EXCELLENT"
    elif final_score >= 68.0:
        cat = "STRONG"
    elif final_score >= 50.0:
        cat = "MODERATE"
    else:
        cat = "WEAK"

    return {
        "score": round(final_score, 1),
        "category": cat,
        "n_touches": n_touches,
        "components": {
            "touch_quality": round(touch_quality_score, 1),
            "reaction_strength": round(reaction_score, 1),
            "pivot_significance": round(pivot_score, 1),
            "geometric_accuracy": round(geometry_score, 1),
            "trend_consistency": round(trend_score, 1),
            "recency": round(recency_score, 1),
        }
    }

async def run_statistical_validation():
    print("=" * 80)
    print("🔬 POINT-IN-TIME STATISTICAL VALIDATION & OUT-OF-SAMPLE AUDIT")
    print("=" * 80)

    # We will accumulate point-in-time tradeable touch events
    train_events = []
    oos_events = []

    # Check Look-Ahead Bias by tracking if any event used future anchors
    look_ahead_violations = 0

    for coin in COINS:
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=1200)
            if not candles or len(candles) < 300:
                continue

            n_total = len(candles)
            train_cutoff = int(n_total * TRAIN_RATIO)

            print(f"Running PIT simulation on {coin} {tf}: {n_total} candles (Train: {train_cutoff}, OOS: {n_total - train_cutoff})...")

            # Pre-compute rolling ATR(14)
            atrs = []
            for i in range(n_total):
                sub = candles[max(0, i - 14): i + 1]
                atrs.append(calculate_atr(sub, period=14))

            # Simulate bar-by-bar progression
            # To avoid redundant lines at every single tick, evaluate every 3 bars or on touches
            last_evaluated_touch_bar = -999

            for t in range(50, n_total - HORIZON):
                atr_t = atrs[t]
                if atr_t <= 0:
                    continue

                candles_up_to_t = candles[:t + 1]
                active_lines = calculate_pit_trendlines(candles_up_to_t, tf, atr_t)

                curr_c = candles[t]
                for line in active_lines:
                    # STRICT POINT-IN-TIME CHECK:
                    # Can only trade a touch at bar t if line was already born (idx2 + right_bars <= t)
                    if line["born_idx"] > t:
                        look_ahead_violations += 1
                        continue

                    # Check if bar t is a touch of this line
                    idx1 = line["p1"]["index"]
                    line_p = line["p1"]["price"] + line["slope"] * (t - idx1)
                    is_res = line["type"] == "resistance_trendline"

                    is_touch = False
                    if is_res:
                        if abs(curr_c["high"] - line_p) <= 0.35 * atr_t and curr_c["close"] <= line_p + 0.25 * atr_t:
                            is_touch = True
                    else:
                        if abs(curr_c["low"] - line_p) <= 0.35 * atr_t and curr_c["close"] >= line_p - 0.25 * atr_t:
                            is_touch = True

                    if not is_touch:
                        continue

                    # Non-overlapping filter: require at least 5 bars separation from last logged touch on this coin/tf
                    if t - last_evaluated_touch_bar < 5:
                        continue
                    last_evaluated_touch_bar = t

                    # Compute Point-In-Time Score (using only data up to t)
                    eval_res = compute_pit_score(candles_up_to_t, line, atr_t, include_sma=True)
                    eval_no_sma = compute_pit_score(candles_up_to_t, line, atr_t, include_sma=False)

                    # Now measure FORWARD OUTCOME strictly over candles[t+1 : t+1+HORIZON]
                    mfe = 0.0
                    mae = 0.0
                    broke = False
                    entry_p = line_p

                    for f in range(1, HORIZON + 1):
                        f_candle = candles[t + f]
                        f_line = line["p1"]["price"] + line["slope"] * (t + f - idx1)

                        if is_res:
                            drop = entry_p - f_candle["low"]
                            if drop > mfe:
                                mfe = drop
                            surge = f_candle["high"] - f_line
                            if surge > mae:
                                mae = surge
                            if f_candle["close"] > f_line + 0.25 * atr_t:
                                broke = True
                        else:
                            rise = f_candle["high"] - entry_p
                            if rise > mfe:
                                mfe = rise
                            breach = f_line - f_candle["low"]
                            if breach > mae:
                                mae = breach
                            if f_candle["close"] < f_line - 0.25 * atr_t:
                                broke = True

                    mfe_atr = mfe / atr_t
                    mae_atr = mae / atr_t
                    clean_bounce = (mfe_atr >= 1.5 and mae_atr <= 0.5)

                    event = {
                        "coin": coin,
                        "tf": tf,
                        "t": t,
                        "n_touches_at_t": eval_res["n_touches"],
                        "score": eval_res["score"],
                        "score_no_sma": eval_no_sma["score"],
                        "category": eval_res["category"],
                        "components": eval_res["components"],
                        "mfe_atr": round(mfe_atr, 3),
                        "mae_atr": round(mae_atr, 3),
                        "broke": broke,
                        "clean_bounce": clean_bounce,
                    }

                    if t < train_cutoff:
                        train_events.append(event)
                    else:
                        oos_events.append(event)

    await hl_client.close()

    print("\n" + "=" * 80)
    print("1. LOOK-AHEAD BIAS AUDIT")
    print("=" * 80)
    print(f"Point-in-time check violations (touches evaluated before anchor confirmation): {look_ahead_violations}")
    assert look_ahead_violations == 0, "Look-Ahead Bias detected!"
    print("✅ ZERO Look-Ahead Bias: 100% of trendline evaluations used only confirmed past data.")

    print("\n" + "=" * 80)
    print(f"2. SAMPLE SPLIT: In-Sample (N={len(train_events)}) | Out-of-Sample (N={len(oos_events)})")
    print("=" * 80)

    # 3. Touch Exhaustion Hypothesis on purely OUT-OF-SAMPLE data
    print("\n" + "=" * 80)
    print("3. TOUCH EXHAUSTION HYPOTHESIS TEST (STRICT OUT-OF-SAMPLE)")
    print("=" * 80)

    oos_by_touch = defaultdict(list)
    for e in oos_events:
        nth = e["n_touches_at_t"]
        if nth == 3:
            k = "Touch #3 (1st live test)"
        elif nth == 4:
            k = "Touch #4 (2nd live test)"
        elif nth >= 5:
            k = "Touch #5+ (Late tests)"
        else:
            k = "Touch #2 (Anchor bar)"
        oos_by_touch[k].append(e)

    for group in ["Touch #3 (1st live test)", "Touch #4 (2nd live test)", "Touch #5+ (Late tests)"]:
        evs = oos_by_touch.get(group, [])
        if not evs:
            continue
        n = len(evs)
        mfes = [e["mfe_atr"] for e in evs]
        mean_mfe = sum(mfes) / n
        std_mfe = math.sqrt(sum((x - mean_mfe)**2 for x in mfes) / max(1, n - 1))
        se_mfe = std_mfe / math.sqrt(n)
        ci_lower = mean_mfe - 1.96 * se_mfe
        ci_upper = mean_mfe + 1.96 * se_mfe

        breakout_rate = sum(1 for e in evs if e["broke"]) / n * 100
        clean_rate = sum(1 for e in evs if e["clean_bounce"]) / n * 100
        mean_mae = sum(e["mae_atr"] for e in evs) / n

        print(f"  • {group:25s} (N={n:3d}):")
        print(f"      Mean MFE: {mean_mfe:4.2f} ATR (95% CI: [{ci_lower:4.2f}, {ci_upper:4.2f}])")
        print(f"      Mean MAE: {mean_mae:4.2f} ATR")
        print(f"      Breakout Rate: {breakout_rate:4.1f}%")
        print(f"      Clean Bounce Rate: {clean_rate:4.1f}%")

    # Statistical significance t-test between Touch #3 and Touch #5+
    evs_t3 = oos_by_touch.get("Touch #3 (1st live test)", [])
    evs_t5 = oos_by_touch.get("Touch #5+ (Late tests)", [])
    if evs_t3 and evs_t5:
        m3 = [e["mfe_atr"] for e in evs_t3]
        m5 = [e["mfe_atr"] for e in evs_t5]
        mean3 = sum(m3) / len(m3)
        mean5 = sum(m5) / len(m5)
        var3 = sum((x - mean3)**2 for x in m3) / (len(m3) - 1)
        var5 = sum((x - mean5)**2 for x in m5) / (len(m5) - 1)
        se_diff = math.sqrt(var3 / len(m3) + var5 / len(m5))
        t_stat = (mean3 - mean5) / max(se_diff, 1e-6)
        print(f"\n  Two-sample t-test (Touch #3 vs Touch #5+ MFE): t = {t_stat:.2f}")

    # 4. PREDICTIVE VALUE OF ADAPTIVE SCORE ON OUT-OF-SAMPLE DATA
    print("\n" + "=" * 80)
    print("4. PREDICTIVE VALUE OF SCORE CATEGORIES (OUT-OF-SAMPLE)")
    print("=" * 80)

    oos_by_cat = defaultdict(list)
    for e in oos_events:
        oos_by_cat[e["category"]].append(e)

    for cat in ["EXCELLENT", "STRONG", "MODERATE", "WEAK"]:
        evs = oos_by_cat.get(cat, [])
        if not evs:
            print(f"  • {cat:10s} (N=  0): No observations")
            continue
        n = len(evs)
        mfes = [e["mfe_atr"] for e in evs]
        mean_mfe = sum(mfes) / n
        se_mfe = (math.sqrt(sum((x - mean_mfe)**2 for x in mfes) / max(1, n - 1))) / math.sqrt(n)
        ci_mfe = f"[{mean_mfe - 1.96*se_mfe:.2f}, {mean_mfe + 1.96*se_mfe:.2f}]"
        mean_mae = sum(e["mae_atr"] for e in evs) / n
        break_pct = sum(1 for e in evs if e["broke"]) / n * 100
        clean_pct = sum(1 for e in evs if e["clean_bounce"]) / n * 100

        print(f"  • {cat:10s} (N={n:3d}): MFE={mean_mfe:4.2f} ATR {ci_mfe:14s} | MAE={mean_mae:4.2f} ATR | Breakout={break_pct:4.1f}% | Clean Bounce={clean_pct:4.1f}%")

    # 5. MONOTONICITY & CORRELATION
    # Spearman rank correlation between score and mfe_atr
    if len(oos_events) > 10:
        scores = [e["score"] for e in oos_events]
        mfes = [e["mfe_atr"] for e in oos_events]
        n_ev = len(scores)

        # Ranks
        def get_ranks(vals):
            sorted_v = sorted(enumerate(vals), key=lambda x: x[1])
            ranks = [0] * len(vals)
            for r, (idx, _) in enumerate(sorted_v):
                ranks[idx] = r + 1
            return ranks

        r_score = get_ranks(scores)
        r_mfe = get_ranks(mfes)
        d_sq = sum((r_score[i] - r_mfe[i])**2 for i in range(n_ev))
        spearman_rho = 1.0 - (6.0 * d_sq) / (n_ev * (n_ev**2 - 1))
        print(f"\n  Spearman Rank Correlation (Score vs Forward MFE): ρ = {spearman_rho:+.3f}")

    # 6. COMPONENT ABLATION (WITH SMA-50 vs WITHOUT SMA-50)
    print("\n" + "=" * 80)
    print("5. ABLATION STUDY: TREND CONSISTENCY (SMA-50)")
    print("=" * 80)
    # Check correlation of Score with SMA vs Score without SMA
    scores_with = [e["score"] for e in oos_events]
    scores_no = [e["score_no_sma"] for e in oos_events]
    r_with = get_ranks(scores_with)
    r_no = get_ranks(scores_no)
    d_sq_with = sum((r_with[i] - r_mfe[i])**2 for i in range(n_ev))
    d_sq_no = sum((r_no[i] - r_mfe[i])**2 for i in range(n_ev))
    rho_with = 1.0 - (6.0 * d_sq_with) / (n_ev * (n_ev**2 - 1))
    rho_no = 1.0 - (6.0 * d_sq_no) / (n_ev * (n_ev**2 - 1))
    print(f"  Spearman ρ WITH SMA-50:    {rho_with:+.3f}")
    print(f"  Spearman ρ WITHOUT SMA-50: {rho_no:+.3f}")

    # 7. ADAPTABILITY ACROSS ASSETS
    print("\n" + "=" * 80)
    print("6. ADAPTABILITY ACROSS ASSET CLASSES (OUT-OF-SAMPLE)")
    print("=" * 80)
    oos_by_coin = defaultdict(list)
    for e in oos_events:
        oos_by_coin[e["coin"]].append(e)

    for c in COINS:
        evs = oos_by_coin.get(c, [])
        if not evs:
            continue
        avg_mfe = sum(e["mfe_atr"] for e in evs) / len(evs)
        avg_mae = sum(e["mae_atr"] for e in evs) / len(evs)
        clean = sum(1 for e in evs if e["clean_bounce"]) / len(evs) * 100
        print(f"  • {c:5s} (N={len(evs):3d}): Avg MFE={avg_mfe:4.2f} ATR | Avg MAE={avg_mae:4.2f} ATR | Clean Bounce={clean:4.1f}%")

if __name__ == "__main__":
    asyncio.run(run_statistical_validation())
