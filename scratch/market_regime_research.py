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
    TIMEFRAME_SWING_CONFIG,
)
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
    resolve_research_timeframes,
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

def classify_market_regime(candles_up_to_t, t, atr_series):
    """
    Classifies market regime point-in-time at bar t using multiple mathematical models:
    1. Trend Efficiency Ratio (ER = |Close_t - Close_{t-20}| / sum(|Close_i - Close_{i-1}|))
    2. EMA-20 vs EMA-50 slope and alignment
    3. Volatility percentile: ATR(14)_t / Median(ATR(14)_{t-100:t})
    Regimes:
      - TRENDING_UP
      - TRENDING_DOWN
      - RANGING_LOW_VOL
      - RANGING_HIGH_VOL
      - TRANSITIONAL
    """
    n = len(candles_up_to_t)
    if n < 50:
        return "TRANSITIONAL", 0.0, 1.0

    # 1. Trend Efficiency Ratio (20 bars)
    span = min(20, n - 1)
    net_change = candles_up_to_t[-1]["close"] - candles_up_to_t[-1 - span]["close"]
    gross_change = sum(abs(candles_up_to_t[k]["close"] - candles_up_to_t[k-1]["close"]) for k in range(n - span, n))
    er = abs(net_change) / max(gross_change, 1e-6)

    # 2. Moving average alignment (20 vs 50)
    c20 = [c["close"] for c in candles_up_to_t[-20:]]
    c50 = [c["close"] for c in candles_up_to_t[-min(50, n):]]
    ma20 = sum(c20) / len(c20)
    ma50 = sum(c50) / len(c50)

    # 3. Volatility Ratio relative to 80-bar rolling median ATR
    curr_atr = atr_series[t]
    hist_atrs = atr_series[max(0, t - 80): t + 1]
    sorted_atrs = sorted(hist_atrs)
    med_atr = sorted_atrs[len(sorted_atrs) // 2] if sorted_atrs else curr_atr
    vol_ratio = curr_atr / max(med_atr, 1e-6)

    is_high_vol = vol_ratio > 1.15
    is_low_vol = vol_ratio < 0.85

    # Regime synthesis:
    if er > 0.40 and ma20 > ma50 and net_change > 0:
        regime = "TRENDING_UP"
    elif er > 0.40 and ma20 < ma50 and net_change < 0:
        regime = "TRENDING_DOWN"
    elif er < 0.28:
        regime = "RANGING_HIGH_VOL" if is_high_vol else "RANGING_LOW_VOL"
    else:
        regime = "TRANSITIONAL"

    return regime, round(er, 3), round(vol_ratio, 3)

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

async def run_market_regime_research():
    print("=" * 90)
    print("MODULE A: MARKET REGIME DETECTION & TRENDLINE INTERACTION RESEARCH")
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

            atr_series = []
            for i in range(n):
                sub = candles[max(0, i - 14): i + 1]
                atr_series.append(calculate_atr(sub, 14))

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

                    # Touch check
                    if is_res:
                        is_touch = abs(curr_c["high"] - lp) <= 0.35 * a_t and curr_c["close"] <= lp + 0.25 * a_t
                    else:
                        is_touch = abs(curr_c["low"] - lp) <= 0.35 * a_t and curr_c["close"] >= lp - 0.25 * a_t

                    if not is_touch: continue
                    if t - last_eval < 4: continue
                    last_eval = t

                    regime, er, vol_ratio = classify_market_regime(candles_up_to_t, t, atr_series)

                    # Directional alignment:
                    # Support is aligned with TRENDING_UP; Resistance aligned with TRENDING_DOWN.
                    if (is_res and regime == "TRENDING_DOWN") or (not is_res and regime == "TRENDING_UP"):
                        alignment = "WITH_TREND"
                    elif (is_res and regime == "TRENDING_UP") or (not is_res and regime == "TRENDING_DOWN"):
                        alignment = "COUNTER_TREND"
                    else:
                        alignment = "NEUTRAL_RANGING"

                    # Forward metrics over HORIZON
                    mfe = 0.0
                    mae = 0.0
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
                        "type": line["type"],
                        "regime": regime,
                        "alignment": alignment,
                        "er": er,
                        "vol_ratio": vol_ratio,
                        "is_oos": (t >= train_cutoff),
                        "mfe_atr": round(mfe_atr, 3),
                        "mae_atr": round(mae_atr, 3),
                        "broke": broke,
                        "clean_bounce": clean_bounce,
                    })

    await hl_client.close()

    oos = [e for e in all_events if e["is_oos"]]
    print(f"Total Touch Events with Regime Classification: N = {len(all_events)} (Train: {len(all_events)-len(oos)}, OOS: {len(oos)})")

    print("\n" + "=" * 90)
    print("1. OUT-OF-SAMPLE RESULTS BY REGIME ALIGNMENT (WITH-TREND vs COUNTER-TREND vs RANGING)")
    print("=" * 90)
    print(f"{'Alignment':<18} | {'N':<5} | {'Clean Bounce % [95% CI]':<26} | {'Breakout % [95% CI]':<26} | {'MFE (ATR)':<10} | {'MAE (ATR)'}")
    print("-" * 110)

    for alg in ["WITH_TREND", "COUNTER_TREND", "NEUTRAL_RANGING"]:
        sub = [e for e in oos if e["alignment"] == alg]
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"{alg:<18} | {len(sub):<5} | {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%]  | {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%]  | {mfe_m:6.2f}     | {mae_m:6.2f}")

    print("\n" + "=" * 90)
    print("2. OUT-OF-SAMPLE RESULTS BY DETAILED REGIME CLUSTER")
    print("=" * 90)
    print(f"{'Regime':<20} | {'N':<5} | {'Clean Bounce % [95% CI]':<26} | {'Breakout % [95% CI]':<26} | {'MFE':<6} | {'MAE'}")
    print("-" * 105)

    regimes = ["TRENDING_UP", "TRENDING_DOWN", "RANGING_LOW_VOL", "RANGING_HIGH_VOL", "TRANSITIONAL"]
    for reg in regimes:
        sub = [e for e in oos if e["regime"] == reg]
        if not sub: continue
        cb_m, cb_l, cb_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["clean_bounce"])/len(evs)*100.0)
        bk_m, bk_l, bk_h = clustered_bootstrap_ci(sub, lambda evs: sum(1 for e in evs if e["broke"])/len(evs)*100.0)
        mfe_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mfe_atr"] for e in evs)/len(evs))
        mae_m, _, _ = clustered_bootstrap_ci(sub, lambda evs: sum(e["mae_atr"] for e in evs)/len(evs))
        print(f"{reg:<20} | {len(sub):<5} | {cb_m:4.1f}% [{cb_l:4.1f}% - {cb_h:4.1f}%]  | {bk_m:4.1f}% [{bk_l:4.1f}% - {bk_h:4.1f}%]  | {mfe_m:4.2f} | {mae_m:4.2f}")

if __name__ == "__main__":
    asyncio.run(run_market_regime_research())
