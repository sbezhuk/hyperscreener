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
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
    resolve_research_timeframes,
)

THRESHOLDS = [0.55, 0.65, 0.75, 0.85]
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
            lines.append({
                "id": f"res_{p1['time']}_{p2['time']}",
                "type": "resistance",
                "p1": p1,
                "p2": p2,
                "slope": slope,
                "born_idx": p2["index"] + right_bars,
            })

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
            lines.append({
                "id": f"sup_{p1['time']}_{p2['time']}",
                "type": "support",
                "p1": p1,
                "p2": p2,
                "slope": slope,
                "born_idx": p2["index"] + right_bars,
            })
    return lines

def clustered_bootstrap_ratio(events, pred_fn, num_bootstraps=BOOTSTRAP_REPLICATIONS, seed=RANDOM_SEED):
    if not events: return 0.0, 0.0, 0.0
    clusters = defaultdict(list)
    for e in events:
        clusters[e["line_id"]].append(e)
    keys = list(clusters.keys())
    if not keys: return 0.0, 0.0, 0.0

    rng = random.Random(seed)
    ratios = []
    for _ in range(num_bootstraps):
        sampled = []
        for k in [rng.choice(keys) for _ in range(len(keys))]:
            sampled.extend(clusters[k])
        val = sum(1 for e in sampled if pred_fn(e)) / len(sampled) * 100.0 if sampled else 0.0
        ratios.append(val)
    ratios.sort()
    mean_val = sum(ratios) / len(ratios)
    ci_low = ratios[int(0.025 * num_bootstraps)]
    ci_high = ratios[int(0.975 * num_bootstraps)]
    return mean_val, ci_low, ci_high

async def run_deep_dive():
    print("=" * 90)
    print("🔬 COMPRESSION THRESHOLD VALIDATION & OUT-OF-SAMPLE BOOTSTRAP")
    print("=" * 90)

    all_events = []

    target_coins = await resolve_research_coins(min_volume_usd=5_000_000, top_n=6)
    target_tfs = await resolve_research_timeframes(["15m", "1h", "4h"])
    print(f"Universally discovered assets: {target_coins}")
    print(f"Universally supported timeframes: {target_tfs}")

    for coin in target_coins:
        for tf in target_tfs:
            ds = await get_single_dataset(coin=coin, timeframe=tf, limit=1200)
            candles = ds["candles"]
            if not candles or len(candles) < 200: continue
            n = len(candles)
            train_cutoff = int(n * 0.65)

            atr5, atr20, atr14 = [], [], []
            for i in range(n):
                sub5 = candles[max(0, i - 5): i + 1]
                sub20 = candles[max(0, i - 20): i + 1]
                sub14 = candles[max(0, i - 14): i + 1]
                atr5.append(calculate_atr(sub5, 5))
                atr20.append(calculate_atr(sub20, 20))
                atr14.append(calculate_atr(sub14, 14))

            last_eval = -999
            for t in range(50, n - HORIZON):
                a_t = atr14[t]
                if a_t <= 0 or atr20[t] <= 0: continue
                ratio = atr5[t] / atr20[t]

                candles_up_to_t = candles[:t + 1]
                active_lines = calculate_pit_trendlines(candles_up_to_t, tf, a_t)

                for line in active_lines:
                    if line["born_idx"] > t: continue
                    idx1 = line["p1"]["index"]
                    lp = line["p1"]["price"] + line["slope"] * (t - idx1)
                    is_res = (line["type"] == "resistance")

                    # Near line within 0.40 ATR
                    is_near_3bars = True
                    for k in range(max(0, t - 2), t + 1):
                        k_lp = line["p1"]["price"] + line["slope"] * (k - idx1)
                        if is_res:
                            if abs(candles[k]["high"] - k_lp) > 0.45 * a_t and abs(candles[k]["close"] - k_lp) > 0.45 * a_t:
                                is_near_3bars = False; break
                        else:
                            if abs(candles[k]["low"] - k_lp) > 0.45 * a_t and abs(candles[k]["close"] - k_lp) > 0.45 * a_t:
                                is_near_3bars = False; break

                    if not is_near_3bars: continue
                    if t - last_eval < 4: continue
                    last_eval = t

                    # Measure forward outcome over HORIZON
                    broke = False
                    rejected = False
                    wick_breach = False
                    exit_bar = HORIZON
                    max_move = 0.0

                    for f in range(1, HORIZON + 1):
                        fc = candles[t + f]
                        fl = line["p1"]["price"] + line["slope"] * (t + f - idx1)
                        if is_res:
                            move = abs(fc["close"] - fl) / a_t
                            if move > max_move: max_move = move
                            if fc["close"] > fl + 0.25 * a_t:
                                broke = True
                                exit_bar = f; break
                            elif fc["high"] > fl + 0.25 * a_t and not broke:
                                wick_breach = True
                            elif fl - fc["close"] >= 0.50 * a_t:
                                rejected = True
                                exit_bar = f; break
                        else:
                            move = abs(fc["close"] - fl) / a_t
                            if move > max_move: max_move = move
                            if fc["close"] < fl - 0.25 * a_t:
                                broke = True
                                exit_bar = f; break
                            elif fc["low"] < fl - 0.25 * a_t and not broke:
                                wick_breach = True
                            elif fc["close"] - fl >= 0.50 * a_t:
                                rejected = True
                                exit_bar = f; break

                    all_events.append({
                        "coin": coin,
                        "tf": tf,
                        "line_id": f"{coin}_{tf}_{line['id']}",
                        "type": line["type"],
                        "ratio": ratio,
                        "is_oos": (t >= train_cutoff),
                        "broke": broke,
                        "rejected": rejected,
                        "wick_breach": wick_breach and not broke,
                        "exit_bar": exit_bar,
                        "max_move": max_move,
                    })

    await hl_client.close()

    oos_events = [e for e in all_events if e["is_oos"]]
    print(f"Total Compression Proximity Events: N = {len(all_events)} (Train: {len(all_events)-len(oos_events)}, OOS: {len(oos_events)})")

    print("\n" + "=" * 90)
    print("OUT-OF-SAMPLE CLUSTERED BOOTSTRAP: BREAKOUT RATE BY COMPRESSION THRESHOLD")
    print("=" * 90)
    print(f"{'Threshold':<10} | {'OOS N':<8} | {'Breakout % [95% CI]':<26} | {'Rejection % [95% CI]':<26} | {'False Breach %':<16} | {'Avg Exit Bar'}")
    print("-" * 105)

    for th in THRESHOLDS:
        sub = [e for e in oos_events if e["ratio"] < th]
        if not sub: continue
        b_mean, b_low, b_high = clustered_bootstrap_ratio(sub, lambda e: e["broke"])
        r_mean, r_low, r_high = clustered_bootstrap_ratio(sub, lambda e: e["rejected"])
        w_mean, w_low, w_high = clustered_bootstrap_ratio(sub, lambda e: e["wick_breach"])
        avg_exit = sum(e["exit_bar"] for e in sub) / len(sub)
        print(f"{th:<10.2f} | {len(sub):<8} | {b_mean:4.1f}% [{b_low:4.1f}% - {b_high:4.1f}%]  | {r_mean:4.1f}% [{r_low:4.1f}% - {r_high:4.1f}%]  | {w_mean:4.1f}% [{w_low:4.1f}% - {w_high:4.1f}%] | {avg_exit:5.1f} bars")

    # Subgroups for 0.65 threshold (Support vs Resistance, Timeframes, Assets)
    print("\n" + "-" * 90)
    print("SUBGROUP DEEP-DIVE FOR DEFAULT THRESHOLD θ = 0.65 (OOS)")
    print("-" * 90)
    sub65 = [e for e in oos_events if e["ratio"] < 0.65]
    print(f"Total 0.65 Events: N = {len(sub65)}")

    def print_subgroup(title, sub_evs):
        if not sub_evs: return
        b_m, b_l, b_h = clustered_bootstrap_ratio(sub_evs, lambda e: e["broke"])
        r_m, r_l, r_h = clustered_bootstrap_ratio(sub_evs, lambda e: e["rejected"])
        print(f"  • {title:<22}: N = {len(sub_evs):>3} | Breakout = {b_m:4.1f}% [{b_l:4.1f}% - {b_h:4.1f}%] | Rejection = {r_m:4.1f}% [{r_l:4.1f}% - {r_h:4.1f}%]")

    print_subgroup("Direction: Support", [e for e in sub65 if e["type"] == "support"])
    print_subgroup("Direction: Resistance", [e for e in sub65 if e["type"] == "resistance"])
    for tf in target_tfs:
        print_subgroup(f"TF: {tf}", [e for e in sub65 if e["tf"] == tf])
    for c in target_coins:
        print_subgroup(f"Asset: {c}", [e for e in sub65 if e["coin"] == c])

if __name__ == "__main__":
    asyncio.run(run_deep_dive())
