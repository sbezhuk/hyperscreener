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

COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
TIMEFRAMES = ["15m", "1h"]
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

async def run_liquidity_interaction_research():
    print("=" * 90)
    print("MODULE C: LIQUIDITY INTERACTION & WICK SWEEPS RESEARCH")
    print("=" * 90)

    all_events = []

    for coin in COINS:
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=1200)
            if not candles or len(candles) < 200: continue
            n = len(candles)
            train_cutoff = int(n * 0.65)

            atr_series = [calculate_atr(candles[max(0, i-14):i+1], 14) for i in range(n)]

            last_eval = -999
            for t in range(50, n - HORIZON):
                a_t = atr_series[t]
                if a_t <= 0: continue

                candles_up_to_t = candles[:t + 1]
                active_lines = calculate_pit_trendlines(candles_up_to_t, tf, a_t)
                curr_c = candles[t]

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

                    # Liquidity Interaction Features at touch bar t:
                    # 1. Wick Sweep of line: did the wick penetrate the line (false breach), but body closed safely inside?
                    # Resistance: High > lp, Close <= lp - 0.15 * a_t
                    # Support: Low < lp, Close >= lp + 0.15 * a_t
                    if is_res:
                        is_wick_sweep = (curr_c["high"] > lp and curr_c["close"] <= lp - 0.15 * a_t)
                    else:
                        is_wick_sweep = (curr_c["low"] < lp and curr_c["close"] >= lp + 0.15 * a_t)

                    # 2. Touch Order (count of touches up to t)
                    touch_count = 2
                    for k in range(line["p1"]["index"] + 1, t):
                        k_lp = line["p1"]["price"] + line["slope"] * (k - idx1)
                        if is_res:
                            if abs(candles[k]["high"] - k_lp) <= 0.35 * a_t and candles[k]["close"] <= k_lp + 0.25 * a_t:
                                touch_count += 1
                        else:
                            if abs(candles[k]["low"] - k_lp) <= 0.35 * a_t and candles[k]["close"] >= k_lp - 0.25 * a_t:
                                touch_count += 1

                    # 3. Cluster Density: count of nearby active trendlines on same tf within 1.0 ATR
                    cluster_density = 0
                    for other in active_lines:
                        if other["id"] == line["id"]: continue
                        other_lp = other["p1"]["price"] + other["slope"] * (t - other["p1"]["index"])
                        if abs(other_lp - lp) <= 1.0 * a_t:
                            cluster_density += 1

                    # Forward metrics over HORIZON
                    mfe, mae = 0.0, 0.0
                    broke = False
                    for f in range(1, HORIZON + 1):
                        fc = candles[t + f]
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
                        "tf": tf,
                        "line_id": f"{coin}_{tf}_{line['id']}",
                        "is_wick_sweep": is_wick_sweep,
                        "touch_count": touch_count,
                        "cluster_density": cluster_density,
                        "is_oos": (t >= train_cutoff),
                        "mfe_atr": round(mfe_atr, 3),
                        "mae_atr": round(mae_atr, 3),
                        "broke": broke,
                        "clean_bounce": clean_bounce,
                    })

    await hl_client.close()

    oos = [e for e in all_events if e["is_oos"]]
    print(f"Total Liquidity Touch Events: N = {len(all_events)} (Train: {len(all_events)-len(oos)}, OOS: {len(oos)})")

    print("\n" + "=" * 90)
    print("1. OUT-OF-SAMPLE RESULTS: WICK SWEEP (FALSE BREACH AT ENTRY) vs CLEAN TOUCH")
    print("=" * 90)
    sweep_sub = [e for e in oos if e["is_wick_sweep"]]
    clean_sub = [e for e in oos if not e["is_wick_sweep"]]

    for name, sub in [("Wick Sweep (Trap at Line)", sweep_sub), ("Clean Touch (No Wick Piercing)", clean_sub)]:
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"  • {name:<32}: N = {len(sub):>3} | Clean Bounce = {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%] | Breakout = {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%] | MFE = {mfe_m:.2f} | MAE = {mae_m:.2f}")

    print("\n" + "=" * 90)
    print("2. OUT-OF-SAMPLE RESULTS BY CLUSTER DENSITY (NEARBY CONCURRENT TRENDLINES)")
    print("=" * 90)
    c0 = [e for e in oos if e["cluster_density"] == 0]
    c1plus = [e for e in oos if e["cluster_density"] >= 1]

    for name, sub in [("Isolated Line (Density = 0)", c0), ("Clustered Line (Density >= 1)", c1plus)]:
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"  • {name:<32}: N = {len(sub):>3} | Clean Bounce = {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%] | Breakout = {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%] | MFE = {mfe_m:.2f} | MAE = {mae_m:.2f}")

if __name__ == "__main__":
    asyncio.run(run_liquidity_interaction_research())
