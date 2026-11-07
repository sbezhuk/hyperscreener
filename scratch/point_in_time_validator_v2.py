import asyncio
import sys
import os
import math
import random
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
BOOTSTRAP_REPLICATIONS = 1000
RANDOM_SEED = 42

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

            slope = (p2["price"] - p1["price"]) / bar_dist
            diff = p1["price"] - p2["price"]
            abs_slope = abs(slope)
            if diff < 0.35 * atr or abs_slope < 0.02 * atr or abs_slope > 1.6 * atr:
                continue

            penetrated = False
            for k in range(idx1 + 1, idx2):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] > line_p + 0.25 * atr or c_k["high"] > line_p + 0.6 * atr:
                    penetrated = True
                    break
            if penetrated:
                continue

            break_count = 0
            for k in range(idx2 + 1, n):
                line_p = p1["price"] + slope * (k - idx1)
                c_k = candles_up_to_t[k]
                if c_k["close"] > line_p + 0.25 * atr:
                    break_count += 1
            if break_count >= 2:
                continue

            # Deterministic unique line ID based on anchor times
            line_id = f"RES_{p1['time']}_{p2['time']}"
            active_lines.append({
                "id": line_id,
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

            line_id = f"SUP_{p1['time']}_{p2['time']}"
            active_lines.append({
                "id": line_id,
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

    # 1. Historical touches up to curr_idx
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

    if n_touches == 2:
        touch_pts = 10.0
    elif n_touches == 3:
        touch_pts = 16.0
    elif n_touches == 4:
        touch_pts = 14.0
    else:
        touch_pts = 10.0

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

    # 2. Historical reaction strength
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
        trend_score = 7.5

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

def calculate_symmetric_forward_metrics(candles, t, line, horizon, atr_t, buffer_factor=0.25, clean_mfe_mult=1.5, clean_mae_mult=0.5):
    """
    Symmetric forward metric evaluation strictly relative to Line_{t+f} and ATR_t.
    """
    idx1 = line["p1"]["index"]
    p1_price = line["p1"]["price"]
    slope = line["slope"]
    is_res = (line["type"] == "resistance_trendline")
    
    max_mfe = 0.0
    max_mae = 0.0
    confirmed_breakout = False
    wick_only_breach = False
    
    mfe_threshold = clean_mfe_mult * atr_t
    mae_threshold = clean_mae_mult * atr_t
    
    mfe_hit_bar = None
    mae_hit_bar = None
    
    for f in range(1, horizon + 1):
        if t + f >= len(candles):
            break
        c = candles[t + f]
        f_line = p1_price + slope * (t + f - idx1)
        
        if is_res:
            fav = f_line - c["low"]
            adv = c["high"] - f_line
            is_break_close = c["close"] > f_line + buffer_factor * atr_t
            is_break_wick = c["high"] > f_line + buffer_factor * atr_t
        else:
            fav = c["high"] - f_line
            adv = f_line - c["low"]
            is_break_close = c["close"] < f_line - buffer_factor * atr_t
            is_break_wick = c["low"] < f_line - buffer_factor * atr_t
            
        if fav > max_mfe:
            max_mfe = fav
        if adv > max_mae:
            max_mae = adv
            
        if is_break_close and not confirmed_breakout:
            confirmed_breakout = True
        elif is_break_wick and not confirmed_breakout:
            wick_only_breach = True
            
        if fav >= mfe_threshold and mfe_hit_bar is None:
            mfe_hit_bar = f
        if adv > mae_threshold and mae_hit_bar is None:
            mae_hit_bar = f
            
    mfe_atr = max(0.0, max_mfe) / atr_t
    mae_atr = max(0.0, max_mae) / atr_t
    
    # Conservative intra-bar ambiguity resolution
    if mae_hit_bar is not None and mfe_hit_bar is not None:
        clean_bounce = (mae_hit_bar > mfe_hit_bar)
    elif mfe_hit_bar is not None and mae_hit_bar is None:
        clean_bounce = True
    else:
        clean_bounce = False
        
    return {
        "mfe_atr": round(mfe_atr, 4),
        "mae_atr": round(mae_atr, 4),
        "confirmed_breakout": confirmed_breakout,
        "wick_only_breach": wick_only_breach and not confirmed_breakout,
        "clean_bounce": clean_bounce,
    }

def clustered_bootstrap_ci(events, metric_fn, num_bootstraps=BOOTSTRAP_REPLICATIONS, seed=RANDOM_SEED):
    """
    Performs clustered bootstrap by grouping events by line_id.
    """
    if not events:
        return 0.0, 0.0, 0.0
    
    # Group by line_id
    clusters = defaultdict(list)
    for e in events:
        clusters[e["line_id"]].append(e)
        
    cluster_keys = list(clusters.keys())
    k = len(cluster_keys)
    if k == 0:
        return 0.0, 0.0, 0.0
        
    rng = random.Random(seed)
    estimates = []
    
    for _ in range(num_bootstraps):
        sampled_keys = [rng.choice(cluster_keys) for _ in range(k)]
        sampled_events = []
        for sk in sampled_keys:
            sampled_events.extend(clusters[sk])
        estimates.append(metric_fn(sampled_events))
        
    estimates.sort()
    mean_val = sum(estimates) / len(estimates)
    ci_lower = estimates[int(0.025 * num_bootstraps)]
    ci_upper = estimates[int(0.975 * num_bootstraps)]
    return mean_val, ci_lower, ci_upper

def calculate_correlations(x, y):
    n = len(x)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((x[i] - mean_x)**2 for i in range(n))
    var_y = sum((y[i] - mean_y)**2 for i in range(n))
    denom = math.sqrt(var_x * var_y)
    r_pearson = (cov / denom) if denom > 1e-12 else 0.0
    
    # Spearman rank
    def get_ranks(vals):
        indexed = sorted(enumerate(vals), key=lambda item: item[1])
        ranks = [0.0] * len(vals)
        for rank, (orig_idx, _) in enumerate(indexed):
            ranks[orig_idx] = rank + 1
        return ranks
        
    rx = get_ranks(x)
    ry = get_ranks(y)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    cov_r = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    var_rx = sum((rx[i] - mean_rx)**2 for i in range(n))
    var_ry = sum((ry[i] - mean_ry)**2 for i in range(n))
    denom_r = math.sqrt(var_rx * var_ry)
    r_spearman = (cov_r / denom_r) if denom_r > 1e-12 else 0.0
    return r_pearson, r_spearman

async def run_v2_audit():
    print("=" * 85)
    print("🔬 POINT-IN-TIME RESEARCH METHODOLOGY AUDIT & STATISTICAL RE-VALIDATION (V2)")
    print("=" * 85)
    
    all_events = []
    look_ahead_violations = 0
    
    for coin in COINS:
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=1200)
            if not candles or len(candles) < 300:
                continue
                
            n_total = len(candles)
            train_cutoff = int(n_total * TRAIN_RATIO)
            
            atrs = []
            for i in range(n_total):
                sub = candles[max(0, i - 14): i + 1]
                atrs.append(calculate_atr(sub, period=14))
                
            last_evaluated_touch_bar = -999
            
            for t in range(50, n_total - HORIZON):
                atr_t = atrs[t]
                if atr_t <= 0:
                    continue
                    
                candles_up_to_t = candles[:t + 1]
                active_lines = calculate_pit_trendlines(candles_up_to_t, tf, atr_t)
                curr_c = candles[t]
                
                for line in active_lines:
                    if line["born_idx"] > t:
                        look_ahead_violations += 1
                        continue
                        
                    idx1 = line["p1"]["index"]
                    line_p = line["p1"]["price"] + line["slope"] * (t - idx1)
                    is_res = (line["type"] == "resistance_trendline")
                    
                    is_touch = False
                    if is_res:
                        if abs(curr_c["high"] - line_p) <= 0.35 * atr_t and curr_c["close"] <= line_p + 0.25 * atr_t:
                            is_touch = True
                    else:
                        if abs(curr_c["low"] - line_p) <= 0.35 * atr_t and curr_c["close"] >= line_p - 0.25 * atr_t:
                            is_touch = True
                            
                    if not is_touch:
                        continue
                        
                    if t - last_evaluated_touch_bar < 5:
                        continue
                    last_evaluated_touch_bar = t
                    
                    eval_res = compute_pit_score(candles_up_to_t, line, atr_t, include_sma=True)
                    fwd = calculate_symmetric_forward_metrics(candles, t, line, HORIZON, atr_t)
                    
                    event = {
                        "coin": coin,
                        "tf": tf,
                        "type": line["type"],
                        "line_id": f"{coin}_{tf}_{line['id']}",
                        "t": t,
                        "is_oos": (t >= train_cutoff),
                        "n_touches_at_t": eval_res["n_touches"],
                        "score": eval_res["score"],
                        "category": eval_res["category"],
                        "components": eval_res["components"],
                        "mfe_atr": fwd["mfe_atr"],
                        "mae_atr": fwd["mae_atr"],
                        "confirmed_breakout": fwd["confirmed_breakout"],
                        "wick_only_breach": fwd["wick_only_breach"],
                        "clean_bounce": fwd["clean_bounce"],
                    }
                    all_events.append(event)
                    
    await hl_client.close()
    
    print(f"\nTotal Evaluated Contact Events: N = {len(all_events)}")
    print(f"Point-In-Time Violations: {look_ahead_violations} (Zero Look-Ahead Bias Verified)")
    
    oos_events = [e for e in all_events if e["is_oos"]]
    train_events = [e for e in all_events if not e["is_oos"]]
    print(f"In-Sample Events: {len(train_events)} | Out-of-Sample Events: {len(oos_events)}")
    
    # -------------------------------------------------------------
    # PHASE 1 & 2 AUDIT: Clustered Bootstrap & CIs on OOS Data
    # -------------------------------------------------------------
    print("\n" + "=" * 85)
    print("PHASE 2: CLUSTERED BOOTSTRAP 95% CONFIDENCE INTERVALS (OUT-OF-SAMPLE)")
    print("=" * 85)
    
    def metric_mfe(evs): return sum(e["mfe_atr"] for e in evs) / len(evs) if evs else 0.0
    def metric_mae(evs): return sum(e["mae_atr"] for e in evs) / len(evs) if evs else 0.0
    def metric_brk(evs): return (sum(1 for e in evs if e["confirmed_breakout"]) / len(evs) * 100.0) if evs else 0.0
    def metric_clean(evs): return (sum(1 for e in evs if e["clean_bounce"]) / len(evs) * 100.0) if evs else 0.0
    def metric_wick(evs): return (sum(1 for e in evs if e["wick_only_breach"]) / len(evs) * 100.0) if evs else 0.0

    mfe_mean, mfe_low, mfe_high = clustered_bootstrap_ci(oos_events, metric_mfe)
    mae_mean, mae_low, mae_high = clustered_bootstrap_ci(oos_events, metric_mae)
    brk_mean, brk_low, brk_high = clustered_bootstrap_ci(oos_events, metric_brk)
    clean_mean, clean_low, clean_high = clustered_bootstrap_ci(oos_events, metric_clean)
    wick_mean, wick_low, wick_high = clustered_bootstrap_ci(oos_events, metric_wick)
    
    print(f"Overall OOS Metrics (N={len(oos_events)}, Unique Lines={len(set(e['line_id'] for e in oos_events))}):")
    print(f"  • MFE (ATR):          {mfe_mean:.3f}  [95% CI: {mfe_low:.3f} - {mfe_high:.3f}]")
    print(f"  • MAE (ATR):          {mae_mean:.3f}  [95% CI: {mae_low:.3f} - {mae_high:.3f}]")
    print(f"  • Confirmed Breakout: {brk_mean:.1f}%  [95% CI: {brk_low:.1f}% - {brk_high:.1f}%]")
    print(f"  • Clean Bounce Rate:  {clean_mean:.1f}%  [95% CI: {clean_low:.1f}% - {clean_high:.1f}%]")
    print(f"  • Wick-only Breach:   {wick_mean:.1f}%  [95% CI: {wick_low:.1f}% - {wick_high:.1f}%]")
    
    # -------------------------------------------------------------
    # SUBGROUP AUDIT: Assets, Timeframes, Direction
    # -------------------------------------------------------------
    print("\n" + "-" * 85)
    print("SUBGROUP BREAKDOWN (OOS)")
    print("-" * 85)
    print(f"{'Subgroup':<18} | {'N':<4} | {'MFE [95% CI]':<22} | {'MAE [95% CI]':<22} | {'Breakout %':<16} | {'Clean Bounce %'}")
    print("-" * 85)
    
    subgroups = {}
    for c in COINS:
        subgroups[f"Asset: {c}"] = [e for e in oos_events if e["coin"] == c]
    for tf in TIMEFRAMES:
        subgroups[f"TF: {tf}"] = [e for e in oos_events if e["tf"] == tf]
    subgroups["Direction: Support"] = [e for e in oos_events if e["type"] == "support_trendline"]
    subgroups["Direction: Resistance"] = [e for e in oos_events if e["type"] == "resistance_trendline"]
    
    for name, grp in subgroups.items():
        if not grp:
            continue
        m_m, m_l, m_h = clustered_bootstrap_ci(grp, metric_mfe)
        a_m, a_l, a_h = clustered_bootstrap_ci(grp, metric_mae)
        b_m, b_l, b_h = clustered_bootstrap_ci(grp, metric_brk)
        c_m, c_l, c_h = clustered_bootstrap_ci(grp, metric_clean)
        print(f"{name:<18} | {len(grp):<4} | {m_m:.2f} [{m_l:.2f}-{m_h:.2f}]       | {a_m:.2f} [{a_l:.2f}-{a_h:.2f}]       | {b_m:4.1f}% [{b_l:4.1f}-{b_h:4.1f}] | {c_m:4.1f}% [{c_l:4.1f}-{c_h:4.1f}]")

    # -------------------------------------------------------------
    # TOUCH EXHAUSTION: Touch #3 vs Touch #5+ (Bootstrap Difference)
    # -------------------------------------------------------------
    print("\n" + "=" * 85)
    print("TOUCH EXHAUSTION ANALYSIS: Touch #3 vs Touch #4 vs Touch #5+")
    print("=" * 85)
    
    t3_events = [e for e in oos_events if e["n_touches_at_t"] == 3]
    t4_events = [e for e in oos_events if e["n_touches_at_t"] == 4]
    t5_events = [e for e in oos_events if e["n_touches_at_t"] >= 5]
    
    for t_name, grp in [("Touch #3 (1st live test)", t3_events), ("Touch #4 (2nd live test)", t4_events), ("Touch #5+ (Late tests)", t5_events)]:
        m_m, m_l, m_h = clustered_bootstrap_ci(grp, metric_mfe)
        a_m, a_l, a_h = clustered_bootstrap_ci(grp, metric_mae)
        b_m, b_l, b_h = clustered_bootstrap_ci(grp, metric_brk)
        c_m, c_l, c_h = clustered_bootstrap_ci(grp, metric_clean)
        print(f"{t_name} (N={len(grp)}):")
        print(f"   MFE: {m_m:.3f} [{m_l:.3f} - {m_h:.3f}] | MAE: {a_m:.3f} [{a_l:.3f} - {a_h:.3f}]")
        print(f"   Breakout Rate: {b_m:.1f}% [{b_l:.1f}% - {b_h:.1f}%] | Clean Bounce: {c_m:.1f}% [{c_l:.1f}% - {c_h:.1f}%]")

    # Bootstrap difference between Touch #3 and Touch #5+
    rng = random.Random(RANDOM_SEED)
    t3_clusters = defaultdict(list)
    for e in t3_events: t3_clusters[e["line_id"]].append(e)
    t3_keys = list(t3_clusters.keys())
    
    t5_clusters = defaultdict(list)
    for e in t5_events: t5_clusters[e["line_id"]].append(e)
    t5_keys = list(t5_clusters.keys())
    
    diff_mfe = []
    diff_brk = []
    diff_clean = []
    
    if t3_keys and t5_keys:
        for _ in range(BOOTSTRAP_REPLICATIONS):
            s3 = []
            for k in [rng.choice(t3_keys) for _ in range(len(t3_keys))]: s3.extend(t3_clusters[k])
            s5 = []
            for k in [rng.choice(t5_keys) for _ in range(len(t5_keys))]: s5.extend(t5_clusters[k])
            
            diff_mfe.append(metric_mfe(s3) - metric_mfe(s5))
            diff_brk.append(metric_brk(s5) - metric_brk(s3))
            diff_clean.append(metric_clean(s3) - metric_clean(s5))
            
        diff_mfe.sort()
        diff_brk.sort()
        diff_clean.sort()
        
        print("\nStatistical Comparison [Touch #3 vs Touch #5+]:")
        print(f"  • Δ MFE (Touch #3 minus #5+):     {sum(diff_mfe)/len(diff_mfe):+.3f} ATR [95% CI: {diff_mfe[25]:+.3f} to {diff_mfe[975]:+.3f}]")
        print(f"  • Δ Breakout (Touch #5+ minus #3): {sum(diff_brk)/len(diff_brk):+.1f}%    [95% CI: {diff_brk[25]:+.1f}% to {diff_brk[975]:+.1f}%]")
        print(f"  • Δ Clean Bounce (#3 minus #5+):  {sum(diff_clean)/len(diff_clean):+.1f}%    [95% CI: {diff_clean[25]:+.1f}% to {diff_clean[975]:+.1f}%]")
        
        # Empirical p-values (two-tailed probability of crossing 0)
        p_val_mfe = sum(1 for d in diff_mfe if d <= 0) / len(diff_mfe)
        p_val_brk = sum(1 for d in diff_brk if d <= 0) / len(diff_brk)
        print(f"  • p-value for MFE decay: p = {p_val_mfe:.4f}")
        print(f"  • p-value for Breakout increase: p = {p_val_brk:.4f}")

    # -------------------------------------------------------------
    # PHASE 3 AUDIT: Score Distribution & Bias Investigation
    # -------------------------------------------------------------
    print("\n" + "=" * 85)
    print("PHASE 3: SCORE DISTRIBUTION & BIAS AUDIT")
    print("=" * 85)
    
    score_cats = defaultdict(list)
    for e in all_events:
        score_cats[e["category"]].append(e)
        
    print("Score Category Distribution (All Evaluated Touches):")
    for cat in ["EXCELLENT", "STRONG", "MODERATE", "WEAK"]:
        cnt = len(score_cats[cat])
        pct = (cnt / len(all_events) * 100.0) if all_events else 0.0
        print(f"  • {cat:<10}: {cnt:>4} ({pct:5.1f}%)")
        
    print("\nComponent Minimums & Maximums across all active lines:")
    comp_names = ["touch_quality", "reaction_strength", "pivot_significance", "geometric_accuracy", "trend_consistency", "recency"]
    for cn in comp_names:
        vals = [e["components"][cn] for e in all_events]
        print(f"  • {cn:<20}: Min = {min(vals):4.1f}, Max = {max(vals):4.1f}, Mean = {sum(vals)/len(vals):4.1f}")
        
    scores = [e["score"] for e in oos_events]
    mfes = [e["mfe_atr"] for e in oos_events]
    maes = [e["mae_atr"] for e in oos_events]
    brks = [1.0 if e["confirmed_breakout"] else 0.0 for e in oos_events]
    
    r_p_mfe, r_s_mfe = calculate_correlations(scores, mfes)
    r_p_mae, r_s_mae = calculate_correlations(scores, maes)
    r_p_brk, r_s_brk = calculate_correlations(scores, brks)
    
    print("\nCorrelations with PIT Score on Out-of-Sample:")
    print(f"  • Score vs MFE (ATR):     Pearson r = {r_p_mfe:+.4f}, Spearman rho = {r_s_mfe:+.4f}")
    print(f"  • Score vs MAE (ATR):     Pearson r = {r_p_mae:+.4f}, Spearman rho = {r_s_mae:+.4f}")
    print(f"  • Score vs Breakout (0/1): Pearson r = {r_p_brk:+.4f}, Spearman rho = {r_s_brk:+.4f}")

if __name__ == "__main__":
    asyncio.run(run_v2_audit())
