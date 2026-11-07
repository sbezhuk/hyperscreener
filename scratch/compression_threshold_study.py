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
    TIMEFRAME_SWING_CONFIG,
)

COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
TIMEFRAMES = ["15m", "1h"]
THRESHOLDS = [0.55, 0.65, 0.75, 0.85]
HORIZON = 15

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
            lines.append({"type": "resistance", "p1": p1, "p2": p2, "slope": slope, "born_idx": p2["index"] + right_bars})

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
            lines.append({"type": "support", "p1": p1, "p2": p2, "slope": slope, "born_idx": p2["index"] + right_bars})
    return lines

async def run_compression_study():
    print("=" * 80)
    print("COMPRESSION THRESHOLD EMPIRICAL STUDY: [0.55, 0.65, 0.75, 0.85]")
    print("=" * 80)
    
    # Store events per threshold
    # stats: occurrences, breakouts, non_breakout_moves, breakout_direction, duration_to_exit
    results = {
        th: {
            "all": {"count": 0, "breakouts": 0, "rejections": 0, "durations": []},
            "support": {"count": 0, "breakouts": 0, "rejections": 0},
            "resistance": {"count": 0, "breakouts": 0, "rejections": 0},
            "15m": {"count": 0, "breakouts": 0, "rejections": 0},
            "1h": {"count": 0, "breakouts": 0, "rejections": 0},
        }
        for th in THRESHOLDS
    }

    for coin in COINS:
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=1200)
            if not candles or len(candles) < 300: continue
            n = len(candles)

            # Precalculate rolling ATR(5) and ATR(20)
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
                    c_t = candles[t]

                    # Check proximity within 0.40 * ATR for last 3 bars
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
                    exit_bar = HORIZON
                    for f in range(1, HORIZON + 1):
                        fc = candles[t + f]
                        fl = line["p1"]["price"] + line["slope"] * (t + f - idx1)
                        if is_res:
                            if fc["close"] > fl + 0.25 * a_t:
                                broke = True
                                exit_bar = f; break
                            elif fl - fc["close"] >= 0.5 * a_t:
                                rejected = True
                                exit_bar = f; break
                        else:
                            if fc["close"] < fl - 0.25 * a_t:
                                broke = True
                                exit_bar = f; break
                            elif fc["close"] - fl >= 0.5 * a_t:
                                rejected = True
                                exit_bar = f; break

                    # Record stats for each threshold
                    for th in THRESHOLDS:
                        if ratio < th:
                            r = results[th]
                            r["all"]["count"] += 1
                            if broke: r["all"]["breakouts"] += 1
                            if rejected: r["all"]["rejections"] += 1
                            r["all"]["durations"].append(exit_bar)

                            side = "resistance" if is_res else "support"
                            r[side]["count"] += 1
                            if broke: r[side]["breakouts"] += 1
                            if rejected: r[side]["rejections"] += 1

                            r[tf]["count"] += 1
                            if broke: r[tf]["breakouts"] += 1
                            if rejected: r[tf]["rejections"] += 1

    await hl_client.close()

    print(f"{'Threshold':<10} | {'Occurrences':<12} | {'Breakout %':<12} | {'Rejection %':<12} | {'Avg Bars to Exit':<18} | {'Supp Brk %':<12} | {'Res Brk %'}")
    print("-" * 95)
    for th in THRESHOLDS:
        tot = results[th]["all"]["count"]
        if tot == 0: continue
        brk_pct = results[th]["all"]["breakouts"] / tot * 100.0
        rej_pct = results[th]["all"]["rejections"] / tot * 100.0
        avg_dur = sum(results[th]["all"]["durations"]) / len(results[th]["all"]["durations"])
        
        sup_cnt = results[th]["support"]["count"]
        sup_brk = (results[th]["support"]["breakouts"] / sup_cnt * 100.0) if sup_cnt > 0 else 0.0
        
        res_cnt = results[th]["resistance"]["count"]
        res_brk = (results[th]["resistance"]["breakouts"] / res_cnt * 100.0) if res_cnt > 0 else 0.0
        
        print(f"{th:<10.2f} | {tot:<12} | {brk_pct:9.1f}% | {rej_pct:9.1f}% | {avg_dur:15.1f}  | {sup_brk:9.1f}% | {res_brk:9.1f}%")

    print("\nTimeframe Breakdown:")
    for th in THRESHOLDS:
        c15 = results[th]["15m"]["count"]
        b15 = (results[th]["15m"]["breakouts"] / c15 * 100.0) if c15 > 0 else 0.0
        c1h = results[th]["1h"]["count"]
        b1h = (results[th]["1h"]["breakouts"] / c1h * 100.0) if c1h > 0 else 0.0
        print(f"  Threshold {th:.2f} -> 15m: N={c15}, Breakout={b15:.1f}% | 1h: N={c1h}, Breakout={b1h:.1f}%")

if __name__ == "__main__":
    asyncio.run(run_compression_study())
