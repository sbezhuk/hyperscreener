import asyncio
import sys
import os
import math
from collections import defaultdict

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    detect_timeframe_trendlines,
    find_swings_for_trendlines,
    calculate_atr,
)

TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]

async def run_research():
    print("=" * 80)
    print("🔬 WALK-FORWARD RESEARCH: TRENDLINE QUALITY & MARKET REACTION")
    print("=" * 80)

    score_histogram_current = defaultdict(int)
    total_lines = 0

    # Data collectors for walk-forward touch reaction
    touch_events = []

    for coin in COINS:
        print(f"\nAnalyzing coin: {coin}...")
        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=500)
            if not candles or len(candles) < 50:
                continue

            atr = calculate_atr(candles, period=14)
            if atr <= 0:
                continue

            tls = detect_timeframe_trendlines(candles, interval=tf, include_broken=True, max_lines_per_type=3)
            for tl in tls:
                total_lines += 1
                curr_score = tl["strength"]
                score_bucket = int(curr_score // 10) * 10
                score_histogram_current[score_bucket] += 1

                # Walk-forward study on touches
                idx1 = tl["start_point"]["index"]
                idx2 = tl["end_point"]["index"]
                price1 = tl["start_point"]["price"]
                slope = tl["slope"]
                is_res = tl["line_type"] == "resistance_trendline"

                # Identify all touch points along the line
                n_candles = len(candles)
                for k in range(idx1, n_candles - 5): # Leave at least 5 bars for forward evaluation
                    line_p = price1 + slope * (k - idx1)
                    c_k = candles[k]

                    is_touch = False
                    if is_res:
                        # Price approached resistance within 0.35 ATR and didn't close above
                        if abs(c_k["high"] - line_p) <= 0.35 * atr and c_k["close"] <= line_p + 0.25 * atr:
                            is_touch = True
                    else:
                        # Price approached support within 0.35 ATR and didn't close below
                        if abs(c_k["low"] - line_p) <= 0.35 * atr and c_k["close"] >= line_p - 0.25 * atr:
                            is_touch = True

                    if not is_touch:
                        continue

                    # Walk-forward: measure reaction over next 15 bars (no look-ahead)
                    forward_horizon = min(15, n_candles - 1 - k)
                    if forward_horizon < 3:
                        continue

                    # Track MFE (Maximum Favorable Excursion) & MAE (Maximum Adverse Excursion)
                    entry_p = line_p
                    mfe = 0.0
                    mae = 0.0
                    broke = False
                    bars_to_peak_bounce = 0

                    for f in range(1, forward_horizon + 1):
                        f_candle = candles[k + f]
                        f_line_p = price1 + slope * (k + f - idx1)

                        if is_res:
                            # Favorable is drop down (price moves below line_p)
                            drop = entry_p - f_candle["low"]
                            if drop > mfe:
                                mfe = drop
                                bars_to_peak_bounce = f
                            # Adverse is surge above line
                            surge = f_candle["high"] - f_line_p
                            if surge > mae:
                                mae = surge
                            if f_candle["close"] > f_line_p + 0.25 * atr:
                                broke = True
                        else:
                            # Favorable is bounce up (price moves above line_p)
                            rise = f_candle["high"] - entry_p
                            if rise > mfe:
                                mfe = rise
                                bars_to_peak_bounce = f
                            # Adverse is breach below line
                            breach = f_line_p - f_candle["low"]
                            if breach > mae:
                                mae = breach
                            if f_candle["close"] < f_line_p - 0.25 * atr:
                                broke = True

                    mfe_atr = mfe / atr
                    mae_atr = mae / atr

                    touch_events.append({
                        "coin": coin,
                        "tf": tf,
                        "touch_idx": k,
                        "line_touches_total": tl["touch_count"],
                        "mfe_atr": round(mfe_atr, 2),
                        "mae_atr": round(mae_atr, 2),
                        "bars_to_peak": bars_to_peak_bounce,
                        "broke_in_horizon": broke,
                        "is_res": is_res,
                    })

    await hl_client.close()

    print("\n" + "=" * 80)
    print("📊 1. AUDIT OF CURRENT STRENGTH DISTRIBUTION")
    print("=" * 80)
    print(f"Total lines analyzed: {total_lines}")
    for bucket in sorted(score_histogram_current.keys()):
        cnt = score_histogram_current[bucket]
        pct = (cnt / total_lines * 100) if total_lines else 0
        bar = "█" * int(pct // 3)
        print(f"  Score {bucket:3d} - {bucket+9:3d}: {cnt:3d} lines ({pct:5.1f}%) {bar}")

    print("\n" + "=" * 80)
    print("📈 2. WALK-FORWARD TOUCH PERFORMANCE (BY TOTAL TOUCHES)")
    print("=" * 80)
    print(f"Total touch events evaluated: {len(touch_events)}")

    # Group by line touch count
    by_touch_count = defaultdict(list)
    for ev in touch_events:
        t_group = ev["line_touches_total"]
        if t_group >= 5:
            key = "5+ touches"
        elif t_group == 4:
            key = "4 touches"
        elif t_group == 3:
            key = "3 touches"
        else:
            key = "2 touches"
        by_touch_count[key].append(ev)

    for group in ["2 touches", "3 touches", "4 touches", "5+ touches"]:
        evs = by_touch_count.get(group, [])
        if not evs:
            continue
        avg_mfe = sum(e["mfe_atr"] for e in evs) / len(evs)
        avg_mae = sum(e["mae_atr"] for e in evs) / len(evs)
        break_rate = sum(1 for e in evs if e["broke_in_horizon"]) / len(evs) * 100
        # Win rate: MFE >= 1.5 ATR while MAE <= 0.5 ATR
        clean_bounces = sum(1 for e in evs if e["mfe_atr"] >= 1.5 and e["mae_atr"] <= 0.6) / len(evs) * 100
        print(f"  • {group:10s} (N={len(evs):3d}): Avg MFE={avg_mfe:4.2f} ATR | Avg MAE={avg_mae:4.2f} ATR | Breakout Rate={break_rate:4.1f}% | Clean Bounce (RR>2.5)={clean_bounces:4.1f}%")

    print("\n" + "=" * 80)
    print("🏆 3. PERFORMANCE BY TIMEFRAME")
    print("=" * 80)
    by_tf = defaultdict(list)
    for ev in touch_events:
        by_tf[ev["tf"]].append(ev)

    for tf in TIMEFRAMES:
        evs = by_tf.get(tf, [])
        if not evs:
            continue
        avg_mfe = sum(e["mfe_atr"] for e in evs) / len(evs)
        clean_bounces = sum(1 for e in evs if e["mfe_atr"] >= 1.5 and e["mae_atr"] <= 0.6) / len(evs) * 100
        print(f"  • TF [{tf:3s}] (N={len(evs):3d}): Avg MFE={avg_mfe:4.2f} ATR | Clean Bounce={clean_bounces:4.1f}%")

if __name__ == "__main__":
    asyncio.run(run_research())
