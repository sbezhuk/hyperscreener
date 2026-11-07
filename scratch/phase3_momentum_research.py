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

async def run_momentum_research():
    print("=" * 90)
    print("MODULE D: APPROACH & MOMENTUM INTELLIGENCE RESEARCH")
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

                    if is_res:
                        is_touch = abs(curr_c["high"] - lp) <= 0.35 * a_t and curr_c["close"] <= lp + 0.25 * a_t
                    else:
                        is_touch = abs(curr_c["low"] - lp) <= 0.35 * a_t and curr_c["close"] >= lp - 0.25 * a_t

                    if not is_touch: continue
                    if t - last_eval < 4: continue
                    last_eval = t

                    # 1. Arrival Velocity over last 3 bars (in ATR/bar)
                    c_prev3 = candles[t - 3]
                    lp_prev3 = line["p1"]["price"] + line["slope"] * (t - 3 - idx1)
                    dist_prev3 = abs(c_prev3["close"] - lp_prev3)
                    dist_curr = abs(curr_c["close"] - lp)
                    velocity = (dist_prev3 - dist_curr) / (3.0 * a_t)

                    # 2. Acceleration (velocity change: vel_last_bar minus vel_2bars_ago)
                    c_prev1 = candles[t - 1]
                    lp_prev1 = line["p1"]["price"] + line["slope"] * (t - 1 - idx1)
                    vel_last1 = (abs(c_prev1["close"] - lp_prev1) - dist_curr) / a_t
                    vel_prev = (dist_prev3 - abs(c_prev1["close"] - lp_prev1)) / (2.0 * a_t)
                    acceleration = vel_last1 - vel_prev

                    # 3. Candle Body Expansion (ratio of curr body to 10-bar avg body)
                    curr_body = abs(curr_c["close"] - curr_c["open"])
                    hist_bodies = [abs(candles[k]["close"] - candles[k]["open"]) for k in range(max(0, t - 10), t)]
                    avg_body = sum(hist_bodies) / len(hist_bodies) if hist_bodies else curr_body
                    body_expansion = curr_body / max(avg_body, 1e-6)

                    # 4. Directional Consistency (fraction of last 3 bars closing towards line)
                    towards_count = 0
                    for k in range(t - 2, t + 1):
                        bar_c = candles[k]
                        if is_res and bar_c["close"] >= bar_c["open"]: towards_count += 1
                        elif not is_res and bar_c["close"] <= bar_c["open"]: towards_count += 1
                    dir_consistency = towards_count / 3.0

                    # 5. Volatility Compression
                    sub5 = candles[max(0, t - 5): t + 1]
                    sub20 = candles[max(0, t - 20): t + 1]
                    a5 = calculate_atr(sub5, 5)
                    a20 = calculate_atr(sub20, 20)
                    compression_ratio = a5 / a20 if a20 > 0 else 1.0

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
                        "velocity": round(velocity, 3),
                        "acceleration": round(acceleration, 3),
                        "body_expansion": round(body_expansion, 3),
                        "dir_consistency": round(dir_consistency, 2),
                        "compression_ratio": round(compression_ratio, 3),
                        "is_oos": (t >= train_cutoff),
                        "mfe_atr": round(mfe_atr, 3),
                        "mae_atr": round(mae_atr, 3),
                        "broke": broke,
                        "clean_bounce": clean_bounce,
                    })

    await hl_client.close()

    oos = [e for e in all_events if e["is_oos"]]
    print(f"Total Momentum Touch Events: N = {len(all_events)} (Train: {len(all_events)-len(oos)}, OOS: {len(oos)})")

    # 1. Arrival Velocity: High (> 0.5 ATR/b) vs Normal (0.1 - 0.5) vs Decelerating (<= 0.1)
    print("\n" + "=" * 90)
    print("1. OUT-OF-SAMPLE RESULTS BY ARRIVAL VELOCITY")
    print("=" * 90)
    v_high = [e for e in oos if e["velocity"] > 0.45]
    v_mid = [e for e in oos if 0.10 <= e["velocity"] <= 0.45]
    v_slow = [e for e in oos if e["velocity"] < 0.10]

    for name, sub in [("High Velocity (> 0.45 ATR/b)", v_high), ("Normal Velocity (0.10-0.45 ATR/b)", v_mid), ("Decelerating/Slow (< 0.10 ATR/b)", v_slow)]:
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"  • {name:<35}: N = {len(sub):>3} | Clean Bounce = {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%] | Breakout = {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%] | MFE = {mfe_m:.2f} | MAE = {mae_m:.2f}")

    # 2. Body Expansion: Impulse Candle (> 1.5x) vs Normal Body (<= 1.5x)
    print("\n" + "=" * 90)
    print("2. OUT-OF-SAMPLE RESULTS BY CANDLE BODY EXPANSION")
    print("=" * 90)
    b_exp = [e for e in oos if e["body_expansion"] > 1.5]
    b_norm = [e for e in oos if e["body_expansion"] <= 1.5]

    for name, sub in [("Expanded Body (> 1.5x avg)", b_exp), ("Normal/Small Body (<= 1.5x avg)", b_norm)]:
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"  • {name:<35}: N = {len(sub):>3} | Clean Bounce = {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%] | Breakout = {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%] | MFE = {mfe_m:.2f} | MAE = {mae_m:.2f}")

if __name__ == "__main__":
    asyncio.run(run_momentum_research())
