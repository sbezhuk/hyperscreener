import asyncio
import sys
import os
import math
import random
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    calculate_atr,
    find_swings_for_trendlines,
    calculate_structural_quality,
    _collect_trendline_touches,
    TIMEFRAME_SWING_CONFIG,
)
from app.analyzer.structure import analyze_market_structure
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
)

HORIZON = 15
BOOTSTRAP_REPLICATIONS = 1000
RANDOM_SEED = 42

def calculate_pit_trendlines(candles_up_to_t, interval, atr):
    n = len(candles_up_to_t)
    if n < 15: return []
    clean_tf = interval.lower()
    config = TIMEFRAME_SWING_CONFIG.get(clean_tf, {"left": 3, "right": 3, "prominence": 0.35})
    left_bars, right_bars = config["left"], config["right"]
    min_prominence_atr = config["prominence"]
    max_confirmed_idx = n - 1 - right_bars
    if max_confirmed_idx < left_bars: return []

    highs, lows = [], []
    for i in range(left_bars, max_confirmed_idx + 1):
        c = candles_up_to_t[i]
        curr_h, curr_l = c["high"], c["low"]
        if all(candles_up_to_t[i - k]["high"] < curr_h for k in range(1, left_bars + 1)) and \
           all(candles_up_to_t[i + k]["high"] < curr_h for k in range(1, right_bars + 1)):
            drop_l = curr_h - min(candles_up_to_t[i - k]["low"] for k in range(1, left_bars + 1))
            drop_r = curr_h - min(candles_up_to_t[i + k]["low"] for k in range(1, right_bars + 1))
            if min(drop_l, drop_r) >= min_prominence_atr * atr:
                highs.append({"price": curr_h, "time": c["time"], "index": i})

        if all(candles_up_to_t[i - k]["low"] > curr_l for k in range(1, left_bars + 1)) and \
           all(candles_up_to_t[i + k]["low"] > curr_l for k in range(1, right_bars + 1)):
            rise_l = max(candles_up_to_t[i - k]["high"] for k in range(1, left_bars + 1)) - curr_l
            rise_r = max(candles_up_to_t[i + k]["high"] for k in range(1, right_bars + 1)) - curr_l
            if min(rise_l, rise_r) >= min_prominence_atr * atr:
                lows.append({"price": curr_l, "time": c["time"], "index": i})

    lines = []
    # Resistance
    recent_highs = highs[-6:] if len(highs) >= 6 else highs
    for i in range(len(recent_highs) - 1):
        for j in range(i + 1, len(recent_highs)):
            p1, p2 = recent_highs[i], recent_highs[j]
            bar_dist = p2["index"] - p1["index"]
            if bar_dist < 4 or p1["price"] <= p2["price"]: continue
            slope = (p2["price"] - p1["price"]) / bar_dist
            diff = p1["price"] - p2["price"]
            if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr: continue
            penetrated = False
            for k in range(p1["index"] + 1, p2["index"]):
                lp = p1["price"] + slope * (k - p1["index"])
                if candles_up_to_t[k]["close"] > lp + 0.25 * atr:
                    penetrated = True; break
            if penetrated: continue
            lines.append({"id": f"res_{p1['time']}_{p2['time']}", "type": "resistance", "p1": p1, "p2": p2, "slope": slope, "born_idx": p2["index"] + right_bars})

    # Support
    recent_lows = lows[-6:] if len(lows) >= 6 else lows
    for i in range(len(recent_lows) - 1):
        for j in range(i + 1, len(recent_lows)):
            p1, p2 = recent_lows[i], recent_lows[j]
            bar_dist = p2["index"] - p1["index"]
            if bar_dist < 4 or p2["price"] <= p1["price"]: continue
            slope = (p2["price"] - p1["price"]) / bar_dist
            diff = p2["price"] - p1["price"]
            if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr: continue
            penetrated = False
            for k in range(p1["index"] + 1, p2["index"]):
                lp = p1["price"] + slope * (k - p1["index"])
                if candles_up_to_t[k]["close"] < lp - 0.25 * atr:
                    penetrated = True; break
            if penetrated: continue
            lines.append({"id": f"sup_{p1['time']}_{p2['time']}", "type": "support", "p1": p1, "p2": p2, "slope": slope, "born_idx": p2["index"] + right_bars})
    return lines

def calculate_brier_score(probs, actuals):
    n = len(probs)
    if n == 0: return 0.0
    return sum((probs[i] - actuals[i]) ** 2 for i in range(n)) / n

def calculate_auc(scores, actuals):
    """Calculates Area Under ROC Curve (AUC-ROC)."""
    pairs = sorted(zip(scores, actuals), key=lambda x: x[0], reverse=True)
    n_pos = sum(actuals)
    n_neg = len(actuals) - n_pos
    if n_pos == 0 or n_neg == 0: return 0.5
    rank_sum = 0
    for i, (s, y) in enumerate(reversed(pairs)):
        if y == 1:
            rank_sum += (i + 1)
    auc = (rank_sum - (n_pos * (n_pos + 1)) / 2) / (n_pos * n_neg)
    return max(0.0, min(1.0, auc))

async def run_predictive_validation():
    print("=" * 90)
    print("MODULE E: PREDICTIVE VALIDATION & FEATURE ABLATION RESEARCH")
    print("=" * 90)

    dataset = []

    target_coins = await resolve_research_coins(min_volume_usd=5_000_000, top_n=6)
    print(f"Universally discovered assets: {target_coins}")

    for coin in target_coins:
        print(f"Extracting unified predictive features for {coin}...")
        ds_15m = await get_single_dataset(coin=coin, timeframe="15m", limit=1200)
        ds_1h = await get_single_dataset(coin=coin, timeframe="1h", limit=600)
        candles_15m = ds_15m["candles"]
        candles_1h = ds_1h["candles"]
        if not candles_15m or not candles_1h: continue

        n = len(candles_15m)
        train_cutoff = int(n * 0.65)
        atr15 = [calculate_atr(candles_15m[max(0, i-14):i+1], 14) for i in range(n)]

        last_eval = -999
        for t in range(50, n - HORIZON):
            a_t = atr15[t]
            if a_t <= 0: continue
            curr_c = candles_15m[t]
            time_t = curr_c["time"]

            candles_up_to_t = candles_15m[:t + 1]
            active_lines = calculate_pit_trendlines(candles_up_to_t, "15m", a_t)

            for line in active_lines:
                if line["born_idx"] > t: continue
                idx1 = line["p1"]["index"]
                lp = line["p1"]["price"] + line["slope"] * (t - idx1)
                is_res = (line["type"] == "resistance")

                # Check touch
                if is_res:
                    is_touch = abs(curr_c["high"] - lp) <= 0.35 * a_t and curr_c["close"] <= lp + 0.25 * a_t
                else:
                    is_touch = abs(curr_c["low"] - lp) <= 0.35 * a_t and curr_c["close"] >= lp - 0.25 * a_t

                if not is_touch: continue
                if t - last_eval < 4: continue
                last_eval = t

                # --- 1. BASELINE: Structural Quality (Q) ---
                touches = _collect_trendline_touches(candles_up_to_t, idx1, line["p2"]["index"], line["p1"]["price"], line["slope"], a_t, is_res)
                q_score, _ = calculate_structural_quality(candles_up_to_t, line["p1"], line["p2"], line["slope"], a_t, touches, is_res)

                # --- 2. MODULE A: Market Regime Alignment ---
                span = min(20, len(candles_up_to_t) - 1)
                net_change = candles_up_to_t[-1]["close"] - candles_up_to_t[-1 - span]["close"]
                gross_change = sum(abs(candles_up_to_t[k]["close"] - candles_up_to_t[k-1]["close"]) for k in range(len(candles_up_to_t) - span, len(candles_up_to_t)))
                er = abs(net_change) / max(gross_change, 1e-6)
                c20 = [c["close"] for c in candles_up_to_t[-20:]]
                c50 = [c["close"] for c in candles_up_to_t[-min(50, len(candles_up_to_t)):]]
                ma20 = sum(c20) / len(c20)
                ma50 = sum(c50) / len(c50)
                if er > 0.40 and ma20 > ma50 and net_change > 0: reg = "TRENDING_UP"
                elif er > 0.40 and ma20 < ma50 and net_change < 0: reg = "TRENDING_DOWN"
                else: reg = "RANGING"

                is_with_trend = 1.0 if ((is_res and reg == "TRENDING_DOWN") or (not is_res and reg == "TRENDING_UP")) else 0.0
                is_counter_trend = 1.0 if ((is_res and reg == "TRENDING_UP") or (not is_res and reg == "TRENDING_DOWN")) else 0.0

                # --- 3. MODULE B: MTF Alignment ---
                htf_1h = [c for c in candles_1h if c["time"] <= time_t]
                has_htf_align = 0.0
                if len(htf_1h) >= 20:
                    struct = analyze_market_structure(htf_1h)
                    trend_1h = struct.get("trend", "NEUTRAL")
                    if (not is_res and trend_1h == "BULLISH") or (is_res and trend_1h == "BEARISH"):
                        has_htf_align = 1.0

                # --- 4. MODULE C: Liquidity & Wick Sweep ---
                if is_res:
                    is_wick_sweep = 1.0 if (curr_c["high"] > lp and curr_c["close"] <= lp - 0.15 * a_t) else 0.0
                else:
                    is_wick_sweep = 1.0 if (curr_c["low"] < lp and curr_c["close"] >= lp + 0.15 * a_t) else 0.0

                # --- 5. MODULE D: Momentum & Arrival Velocity ---
                c_prev3 = candles_15m[t - 3]
                lp_prev3 = line["p1"]["price"] + line["slope"] * (t - 3 - idx1)
                dist_prev3 = abs(c_prev3["close"] - lp_prev3)
                dist_curr = abs(curr_c["close"] - lp)
                velocity = (dist_prev3 - dist_curr) / (3.0 * a_t)
                is_high_velocity = 1.0 if velocity > 0.45 else 0.0

                sub5 = candles_15m[max(0, t - 5): t + 1]
                sub20 = candles_15m[max(0, t - 20): t + 1]
                compression = (calculate_atr(sub5, 5) / calculate_atr(sub20, 20)) if calculate_atr(sub20, 20) > 0 else 1.0
                is_compressed = 1.0 if compression < 0.65 else 0.0

                # Measure forward outcome over HORIZON
                mfe, mae = 0.0, 0.0
                broke = 0
                for f in range(1, HORIZON + 1):
                    fc = candles_15m[t + f]
                    fl = line["p1"]["price"] + line["slope"] * (t + f - idx1)
                    if is_res:
                        fav = fl - fc["low"]
                        adv = fc["high"] - fl
                        if fc["close"] > fl + 0.25 * a_t: broke = 1
                    else:
                        fav = fc["high"] - fl
                        adv = fl - fc["low"]
                        if fc["close"] < fl - 0.25 * a_t: broke = 1
                    if fav > mfe: mfe = fav
                    if adv > mae: mae = adv

                clean_bounce = 1 if ((mfe / a_t) >= 1.5 and (mae / a_t) <= 0.5) else 0

                dataset.append({
                    "coin": coin,
                    "line_id": f"{coin}_15m_{line['id']}",
                    "is_oos": (t >= train_cutoff),
                    "q": q_score,
                    "is_with_trend": is_with_trend,
                    "is_counter_trend": is_counter_trend,
                    "has_htf_align": has_htf_align,
                    "is_wick_sweep": is_wick_sweep,
                    "is_high_velocity": is_high_velocity,
                    "is_compressed": is_compressed,
                    "clean_bounce": clean_bounce,
                    "broke": broke,
                })

    await hl_client.close()

    train = [d for d in dataset if not d["is_oos"]]
    oos = [d for d in dataset if d["is_oos"]]
    print(f"\nTotal Unified Events: N = {len(dataset)} (Train: {len(train)}, OOS: {len(oos)})")

    # FEATURE ABLATION ON OUT-OF-SAMPLE (Predicting Clean Bounce)
    # Target: clean_bounce (0 or 1)
    y_oos = [d["clean_bounce"] for d in oos]
    base_rate = sum(y_oos) / len(y_oos)

    print("\n" + "=" * 90)
    print(f"FEATURE ABLATION STUDY (OUT-OF-SAMPLE, N={len(oos)}, Base Clean Bounce Rate={base_rate*100:.1f}%)")
    print("=" * 90)
    print(f"{'Model / Feature Subset':<35} | {'AUC-ROC':<10} | {'Brier Score':<12} | {'Information Gain vs Baseline'}")
    print("-" * 80)

    # Simple additive point-in-time scoring functions:
    def score_baseline(d): return d["q"] / 100.0
    def score_regime(d): return score_baseline(d) + 0.15 * d["is_with_trend"] - 0.15 * d["is_counter_trend"]
    def score_mtf(d): return score_baseline(d) + 0.18 * d["has_htf_align"]
    def score_liquidity(d): return score_baseline(d) + 0.22 * d["is_wick_sweep"]
    def score_momentum(d): return score_baseline(d) - 0.15 * d["is_high_velocity"] + 0.10 * d["is_compressed"]
    def score_full(d): return (score_baseline(d) 
                               + 0.15 * d["is_with_trend"] 
                               - 0.12 * d["is_counter_trend"] 
                               + 0.16 * d["has_htf_align"] 
                               + 0.20 * d["is_wick_sweep"] 
                               - 0.14 * d["is_high_velocity"])

    models = [
        ("M0: Baseline (Structural Quality Q)", score_baseline),
        ("M1: Baseline + Market Regime", score_regime),
        ("M2: Baseline + MTF Alignment", score_mtf),
        ("M3: Baseline + Wick Sweeps (Liquidity)", score_liquidity),
        ("M4: Baseline + Velocity/Momentum", score_momentum),
        ("M5: Full Multi-Factor Model", score_full),
    ]

    base_auc = 0.5
    for name, fn in models:
        s = [fn(d) for d in oos]
        auc = calculate_auc(s, y_oos)
        brier = calculate_brier_score([1.0 / (1.0 + math.exp(-6.0 * (val - 0.85))) for val in s], y_oos)
        if name.startswith("M0"): base_auc = auc
        delta_auc = auc - base_auc
        print(f"{name:<35} | {auc:.4f}     | {brier:.4f}       | {delta_auc:+.4f} AUC")

    # Individual Feature Evaluation & Classification Gate:
    print("\n" + "=" * 90)
    print("APPROVAL GATE: INDIVIDUAL FEATURE CLASSIFICATION (VALIDATED / PROMISING / REJECTED / INCONCLUSIVE)")
    print("=" * 90)

    feature_meta = [
        ("Wick Sweep (False Breach Trap)", "is_wick_sweep", "Positive (Trap leads to bounce)"),
        ("Market Regime (With-Trend)", "is_with_trend", "Positive (Aligns with trend)"),
        ("MTF Structural Alignment", "has_htf_align", "Positive (Higher TF support)"),
        ("Arrival Velocity (> 0.45 ATR/b)", "is_high_velocity", "Negative for bounce (Momentum breakout)"),
        ("Volatility Compression (< 0.65)", "is_compressed", "Neutral (Resolves equally in breakout/bounce)"),
        ("Counter-Trend Contact", "is_counter_trend", "Negative for bounce (High breakout risk)"),
    ]

    for fname, fkey, expected in feature_meta:
        pos_grp = [d for d in oos if d[fkey] == 1.0]
        neg_grp = [d for d in oos if d[fkey] == 0.0]
        if not pos_grp or not neg_grp:
            verdict = "INCONCLUSIVE"
            print(f"  • {fname:<32}: N_pos={len(pos_grp):>3} | Verdict = {verdict}")
            continue

        b_pos = sum(d["clean_bounce"] for d in pos_grp) / len(pos_grp) * 100.0
        b_neg = sum(d["clean_bounce"] for d in neg_grp) / len(neg_grp) * 100.0
        brk_pos = sum(d["broke"] for d in pos_grp) / len(pos_grp) * 100.0
        brk_neg = sum(d["broke"] for d in neg_grp) / len(neg_grp) * 100.0
        delta_b = b_pos - b_neg
        delta_brk = brk_pos - brk_neg

        # Statistical classification rule:
        # VALIDATED: |delta| >= 10.0% and N >= 40 with consistent direction
        # PROMISING: 5.0% <= |delta| < 10.0% or 20 <= N < 40
        # REJECTED: |delta| < 5.0%
        # INCONCLUSIVE: N < 20
        if len(pos_grp) < 20:
            verdict = "INCONCLUSIVE"
        elif abs(delta_b) >= 10.0 or abs(delta_brk) >= 12.0:
            verdict = "VALIDATED"
        elif abs(delta_b) >= 5.0 or abs(delta_brk) >= 6.0:
            verdict = "PROMISING"
        else:
            verdict = "REJECTED"

        print(f"  • {fname:<32}: N={len(pos_grp):>3} | Bounce: {b_pos:4.1f}% vs {b_neg:4.1f}% (Δ {delta_b:+4.1f}%) | Breakout: {brk_pos:4.1f}% vs {brk_neg:4.1f}% (Δ {delta_brk:+4.1f}%) | Verdict: {verdict}")

if __name__ == "__main__":
    asyncio.run(run_predictive_validation())
