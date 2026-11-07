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
    TIMEFRAME_SWING_CONFIG,
)
from app.analyzer.structure import analyze_market_structure

COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
BASE_TF = "15m"
HTF_LIST = ["1h", "4h", "1d"]
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

def clustered_bootstrap_ci(events, pred_fn, num_bootstraps=BOOTSTRAP_REPLICATIONS, seed=RANDOM_SEED):
    if not events: return 0.0, 0.0, 0.0
    clusters = defaultdict(list)
    for e in events: clusters[e["line_id"]].append(e)
    keys = list(clusters.keys())
    if not keys: return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    estimates = []
    for _ in range(num_bootstraps):
        sampled = []
        for k in [rng.choice(keys) for _ in range(len(keys))]: sampled.extend(clusters[k])
        estimates.append(pred_fn(sampled))
    estimates.sort()
    mean_val = sum(estimates) / len(estimates)
    ci_low = estimates[int(0.025 * num_bootstraps)]
    ci_high = estimates[int(0.975 * num_bootstraps)]
    return mean_val, ci_low, ci_high

async def run_mtf_research():
    print("=" * 90)
    print("MODULE B: MULTI-TIMEFRAME (MTF) CONTEXT & CONFLUENCE RESEARCH")
    print("=" * 90)

    all_events = []

    for coin in COINS:
        print(f"Fetching MTF candle datasets for {coin}...")
        c_15m = await hl_client.get_candles(coin=coin, interval="15m", limit=1200)
        c_1h = await hl_client.get_candles(coin=coin, interval="1h", limit=600)
        c_4h = await hl_client.get_candles(coin=coin, interval="4h", limit=300)
        if not c_15m or not c_1h or not c_4h: continue

        n_15m = len(c_15m)
        train_cutoff = int(n_15m * 0.65)

        atr15 = [calculate_atr(c_15m[max(0, i-14):i+1], 14) for i in range(n_15m)]
        atr1h = [calculate_atr(c_1h[max(0, i-14):i+1], 14) for i in range(len(c_1h))]
        atr4h = [calculate_atr(c_4h[max(0, i-14):i+1], 14) for i in range(len(c_4h))]

        last_eval = -999
        for t in range(50, n_15m - HORIZON):
            a_t = atr15[t]
            if a_t <= 0: continue
            c_t = c_15m[t]
            time_t = c_t["time"]

            candles_up_to_t = c_15m[:t + 1]
            active_15m_lines = calculate_pit_trendlines(candles_up_to_t, "15m", a_t)

            for line in active_15m_lines:
                if line["born_idx"] > t: continue
                idx1 = line["p1"]["index"]
                lp = line["p1"]["price"] + line["slope"] * (t - idx1)
                is_res = (line["type"] == "resistance")

                # Contact check on 15m
                if is_res:
                    is_touch = abs(c_t["high"] - lp) <= 0.35 * a_t and c_t["close"] <= lp + 0.25 * a_t
                else:
                    is_touch = abs(c_t["low"] - lp) <= 0.35 * a_t and c_t["close"] >= lp - 0.25 * a_t

                if not is_touch: continue
                if t - last_eval < 4: continue
                last_eval = t

                # POINT-IN-TIME HTF EXTRACTION:
                # Strictly take only 1h and 4h candles with candle['time'] <= time_t
                htf_1h = [c for c in c_1h if c["time"] <= time_t]
                htf_4h = [c for c in c_4h if c["time"] <= time_t]

                has_htf_aligned_trendline = False
                has_htf_confluence = False
                htf_structure_bias = "NEUTRAL"

                if len(htf_1h) >= 20:
                    a_1h = atr1h[min(len(htf_1h) - 1, len(atr1h) - 1)]
                    lines_1h = calculate_pit_trendlines(htf_1h, "1h", a_1h)
                    for l1 in lines_1h:
                        if l1["type"] == line["type"]:
                            has_htf_aligned_trendline = True
                            # Confluence: distance to 1h line price < 1.0 * ATR_15m
                            p1h_at_t = l1["p1"]["price"] + l1["slope"] * (len(htf_1h) - 1 - l1["p1"]["index"])
                            if abs(p1h_at_t - lp) <= 1.0 * a_t:
                                has_htf_confluence = True
                                break

                    # HTF Market Structure (BULLISH vs BEARISH vs NEUTRAL)
                    struct_1h = analyze_market_structure(htf_1h)
                    trend_1h = struct_1h.get("trend", "NEUTRAL")
                    if trend_1h in ("BULLISH", "BEARISH"):
                        htf_structure_bias = trend_1h

                # Determine MTF Concurrence:
                # Aligned: Support with BULLISH HTF or Resistance with BEARISH HTF
                if (not is_res and htf_structure_bias == "BULLISH") or (is_res and htf_structure_bias == "BEARISH"):
                    mtf_alignment = "ALIGNED_WITH_HTF"
                elif (not is_res and htf_structure_bias == "BEARISH") or (is_res and htf_structure_bias == "BULLISH"):
                    mtf_alignment = "AGAINST_HTF"
                else:
                    mtf_alignment = "NEUTRAL_HTF"

                # Forward metrics over 15 bars
                mfe, mae = 0.0, 0.0
                broke = False
                for f in range(1, HORIZON + 1):
                    fc = c_15m[t + f]
                    fl = line["p1"]["price"] + line["slope"] * (t + f - idx1)
                    if is_res:
                        fav = fl - fc["low"]
                        adv = fc["high"] - fl
                        if fc["close"] > fl + 0.25 * a_t: broke = True
                    else:
                        fav = fc["high"] - fl
                        adv = fl - fc["low"]
                        if fc["close"] < fl - 0.25 * a_t: broke = True
                    if fav > mfe: mfe = fav
                    if adv > mae: mae = adv

                mfe_atr = mfe / a_t
                mae_atr = mae / a_t
                clean_bounce = (mfe_atr >= 1.5 and mae_atr <= 0.5)

                all_events.append({
                    "coin": coin,
                    "line_id": f"{coin}_15m_{line['id']}",
                    "type": line["type"],
                    "mtf_alignment": mtf_alignment,
                    "has_htf_aligned_trendline": has_htf_aligned_trendline,
                    "has_htf_confluence": has_htf_confluence,
                    "htf_structure_bias": htf_structure_bias,
                    "is_oos": (t >= train_cutoff),
                    "mfe_atr": round(mfe_atr, 3),
                    "mae_atr": round(mae_atr, 3),
                    "broke": broke,
                    "clean_bounce": clean_bounce,
                })

    await hl_client.close()

    oos = [e for e in all_events if e["is_oos"]]
    print(f"\nTotal MTF Contact Events: N = {len(all_events)} (Train: {len(all_events)-len(oos)}, OOS: {len(oos)})")

    print("\n" + "=" * 90)
    print("1. OUT-OF-SAMPLE RESULTS BY HTF STRUCTURAL ALIGNMENT")
    print("=" * 90)
    print(f"{'MTF Alignment':<20} | {'N':<5} | {'Clean Bounce % [95% CI]':<26} | {'Breakout % [95% CI]':<26} | {'MFE':<6} | {'MAE'}")
    print("-" * 105)

    for alg in ["ALIGNED_WITH_HTF", "AGAINST_HTF", "NEUTRAL_HTF"]:
        sub = [e for e in oos if e["mtf_alignment"] == alg]
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"{alg:<20} | {len(sub):<5} | {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%]  | {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%]  | {mfe_m:4.2f} | {mae_m:4.2f}")

    print("\n" + "=" * 90)
    print("2. OUT-OF-SAMPLE RESULTS BY HTF TRENDLINE CONFLUENCE")
    print("=" * 90)
    sub_conf = [e for e in oos if e["has_htf_confluence"]]
    sub_noconf = [e for e in oos if not e["has_htf_confluence"]]

    for name, sub in [("With HTF Confluence (<=1.0 ATR)", sub_conf), ("Without HTF Confluence", sub_noconf)]:
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"  • {name:<35}: N = {len(sub):>3} | Clean Bounce = {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%] | Breakout = {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%] | MFE = {mfe_m:.2f} | MAE = {mae_m:.2f}")

if __name__ == "__main__":
    asyncio.run(run_mtf_research())
