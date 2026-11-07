import asyncio
import sys
import os
import math
import random
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    find_swings_for_trendlines,
    calculate_atr,
    _evaluate_trendline_candidate,
    detect_timeframe_trendlines,
    TIMEFRAME_SWING_CONFIG,
    DEFAULT_COMPRESSION_THRESHOLD,
)

COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
TIMEFRAMES = ["15m", "1h", "4h"]
BOOTSTRAP_REPLICATIONS = 1000
RANDOM_SEED = 42

def compute_percentiles(vals, pcts=[10, 25, 50, 75, 90]):
    if not vals:
        return {p: 0.0 for p in pcts}
    s = sorted(vals)
    n = len(s)
    res = {}
    for p in pcts:
        idx = int((p / 100.0) * n)
        idx = min(idx, n - 1)
        res[p] = round(s[idx], 2)
    return res

def correlation(x, y):
    n = len(x)
    if n < 2: return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    vx = sum((x[i] - mx)**2 for i in range(n))
    vy = sum((y[i] - my)**2 for i in range(n))
    denom = math.sqrt(vx * vy)
    return cov / denom if denom > 1e-12 else 0.0

async def run_calibration_audit():
    print("=" * 90)
    print("🔬 STRUCTURAL INTELLIGENCE CALIBRATION & DISTRIBUTION AUDIT")
    print("=" * 90)

    all_candidate_lines = []
    top_detected_lines = []
    
    # Track compression events across history
    compression_study_events = []

    for coin in COINS:
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=1200)
            if not candles or len(candles) < 100:
                continue

            n = len(candles)
            atr = calculate_atr(candles, 14)
            if atr <= 0: atr = max(candles[-1]["close"] * 0.01, 0.0001)

            swings = find_swings_for_trendlines(candles, interval=tf, atr=atr)
            highs = swings["highs"]
            lows = swings["lows"]

            # Evaluate all candidate lines across all historical swings
            # Resistance
            for i in range(len(highs) - 1):
                for j in range(i + 1, len(highs)):
                    cand = _evaluate_trendline_candidate(
                        candles=candles,
                        p1=highs[i],
                        p2=highs[j],
                        tl_type="resistance_trendline",
                        interval=tf,
                        atr=atr,
                    )
                    if cand:
                        cand["coin"] = coin
                        cand["tf"] = tf
                        all_candidate_lines.append(cand)

            # Support
            for i in range(len(lows) - 1):
                for j in range(i + 1, len(lows)):
                    cand = _evaluate_trendline_candidate(
                        candles=candles,
                        p1=lows[i],
                        p2=lows[j],
                        tl_type="support_trendline",
                        interval=tf,
                        atr=atr,
                    )
                    if cand:
                        cand["coin"] = coin
                        cand["tf"] = tf
                        all_candidate_lines.append(cand)

            # Also collect the top deduplicated lines produced by production detector
            top_lines = detect_timeframe_trendlines(candles, interval=tf, include_broken=True, max_lines_per_type=3)
            for tl in top_lines:
                tl["coin"] = coin
                tl["tf"] = tf
                top_detected_lines.append(tl)

    await hl_client.close()

    print(f"\n1. SAMPLE SIZE AUDIT:")
    print(f"Total Unique Valid Candidate Lines Evaluated: N = {len(all_candidate_lines)}")
    print(f"Total Top Production Trendlines: N = {len(top_detected_lines)}")

    # -------------------------------------------------------------
    # Q DISTRIBUTION AUDIT
    # -------------------------------------------------------------
    def analyze_q_set(name, lines):
        q_vals = [l["structural_quality"] for l in lines]
        n = len(q_vals)
        mean_q = sum(q_vals) / n
        var_q = sum((x - mean_q)**2 for x in q_vals) / n
        std_q = math.sqrt(var_q)
        pcts = compute_percentiles(q_vals, [10, 25, 50, 75, 90])

        print(f"\n--- {name} (N = {n}) ---")
        print(f"  • Min: {min(q_vals):.1f} | Max: {max(q_vals):.1f} | Mean: {mean_q:.2f} | Median (P50): {pcts[50]:.1f} | StdDev: {std_q:.2f}")
        print(f"  • Percentiles: P10 = {pcts[10]:.1f} | P25 = {pcts[25]:.1f} | P50 = {pcts[50]:.1f} | P75 = {pcts[75]:.1f} | P90 = {pcts[90]:.1f}")
        
        # Histogram bins: <50, 50-65, 65-80, 80-90, 90-100
        bins = {"<50": 0, "50-65": 0, "65-80": 0, "80-90": 0, "90-100": 0}
        for q in q_vals:
            if q < 50: bins["<50"] += 1
            elif q < 65: bins["50-65"] += 1
            elif q < 80: bins["65-80"] += 1
            elif q < 90: bins["80-90"] += 1
            else: bins["90-100"] += 1
        print("  • Histogram Distribution:")
        for b, count in bins.items():
            print(f"    - {b:<8}: {count:>5} ({count/n*100:5.1f}%)")
        return q_vals

    print("\n" + "=" * 90)
    print("PHASE 1: STRUCTURAL QUALITY (Q) DISTRIBUTION & SATURATION AUDIT")
    print("=" * 90)
    all_q = analyze_q_set("ALL HISTORICAL CANDIDATE LINES (FULL POPULATION)", all_candidate_lines)
    top_q = analyze_q_set("TOP DEDUPLICATED PRODUCTION LINES", top_detected_lines)

    # Component Correlations on full population
    print("\nComponent Breakdown & Independence Analysis (All Candidates):")
    prom_vals = [l["structural_quality_components"]["anchor_prominence"] for l in all_candidate_lines]
    spacing_vals = [l["structural_quality_components"]["spacing_regularity"] for l in all_candidate_lines]
    prec_vals = [l["structural_quality_components"]["ray_precision"] for l in all_candidate_lines]
    void_vals = [l["structural_quality_components"]["void_integrity"] for l in all_candidate_lines]

    print(f"  • anchor_prominence (max 30): Min={min(prom_vals):.1f}, Max={max(prom_vals):.1f}, Mean={sum(prom_vals)/len(prom_vals):.1f}, Std={math.sqrt(sum((x-sum(prom_vals)/len(prom_vals))**2 for x in prom_vals)/len(prom_vals)):.2f}")
    print(f"  • spacing_regularity (max 25): Min={min(spacing_vals):.1f}, Max={max(spacing_vals):.1f}, Mean={sum(spacing_vals)/len(spacing_vals):.1f}, Std={math.sqrt(sum((x-sum(spacing_vals)/len(spacing_vals))**2 for x in spacing_vals)/len(spacing_vals)):.2f}")
    print(f"  • ray_precision     (max 25): Min={min(prec_vals):.1f}, Max={max(prec_vals):.1f}, Mean={sum(prec_vals)/len(prec_vals):.1f}, Std={math.sqrt(sum((x-sum(prec_vals)/len(prec_vals))**2 for x in prec_vals)/len(prec_vals)):.2f}")
    print(f"  • void_integrity    (max 20): Min={min(void_vals):.1f}, Max={max(void_vals):.1f}, Mean={sum(void_vals)/len(void_vals):.1f}, Std={math.sqrt(sum((x-sum(void_vals)/len(void_vals))**2 for x in void_vals)/len(void_vals)):.2f}")

    print("\nComponent Correlation Matrix with Total Q:")
    print(f"  • Corr(Q, anchor_prominence):  r = {correlation(all_q, prom_vals):+.4f}")
    print(f"  • Corr(Q, spacing_regularity): r = {correlation(all_q, spacing_vals):+.4f}")
    print(f"  • Corr(Q, ray_precision):     r = {correlation(all_q, prec_vals):+.4f}")
    print(f"  • Corr(Q, void_integrity):    r = {correlation(all_q, void_vals):+.4f}")

    print("\nInter-Component Correlations (Testing Independent Information Contribution):")
    print(f"  • Corr(prominence, spacing):   r = {correlation(prom_vals, spacing_vals):+.4f}")
    print(f"  • Corr(prominence, precision): r = {correlation(prom_vals, prec_vals):+.4f}")
    print(f"  • Corr(prominence, void):      r = {correlation(prom_vals, void_vals):+.4f}")
    print(f"  • Corr(spacing, precision):    r = {correlation(spacing_vals, prec_vals):+.4f}")
    print(f"  • Corr(spacing, void):         r = {correlation(spacing_vals, void_vals):+.4f}")
    print(f"  • Corr(precision, void):       r = {correlation(prec_vals, void_vals):+.4f}")

    # Breakdown by Asset & Timeframe
    print("\nBreakdown by Asset (Mean Q & Sample):")
    for c in COINS:
        c_lines = [l for l in all_candidate_lines if l["coin"] == c]
        if c_lines:
            c_q = [l["structural_quality"] for l in c_lines]
            print(f"  • Asset {c:<5}: N = {len(c_lines):>4} | Mean Q = {sum(c_q)/len(c_q):.2f} | Min = {min(c_q):.1f} | Max = {max(c_q):.1f}")

    print("\nBreakdown by Timeframe (Mean Q & Sample):")
    for tf in TIMEFRAMES:
        tf_lines = [l for l in all_candidate_lines if l["tf"] == tf]
        if tf_lines:
            tf_q = [l["structural_quality"] for l in tf_lines]
            print(f"  • TF {tf:<4}: N = {len(tf_lines):>4} | Mean Q = {sum(tf_q)/len(tf_q):.2f} | Min = {min(tf_q):.1f} | Max = {max(tf_q):.1f}")

    # Breakdown by State
    print("\nBreakdown by Market Interaction State (Candidate Lines):")
    by_st = defaultdict(list)
    for l in all_candidate_lines:
        by_st[l["interaction_state"]].append(l["structural_quality"])
    for st, q_list in sorted(by_st.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  • {st:<14}: N = {len(q_list):>4} ({len(q_list)/len(all_candidate_lines)*100:5.1f}%) | Mean Q = {sum(q_list)/len(q_list):.1f} | Min = {min(q_list):.1f} | Max = {max(q_list):.1f}")

if __name__ == "__main__":
    asyncio.run(run_calibration_audit())
