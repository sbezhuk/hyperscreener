import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    detect_timeframe_trendlines,
    find_swings_for_trendlines,
    calculate_atr,
)
from app.analyzer.mtf_trendline import MTFTrendlineManager

TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]
COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]

async def run_audit():
    print("=" * 80)
    print("🚀 STARTING E2E AUDIT: INDEPENDENT TRENDLINES ON REAL MARKET DATA")
    print("=" * 80)

    mgr = MTFTrendlineManager()
    total_lines = 0
    issues = []
    regimes_checked = {}

    for coin in COINS:
        print(f"\n🪙 Auditing coin: {coin} across {len(TIMEFRAMES)} timeframes...")
        timeframe_lines_map = {}

        for tf in TIMEFRAMES:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=300)
            if not candles or len(candles) < 20:
                print(f"  ⚠️ [{tf}] Insufficient candle data ({len(candles) if candles else 0} bars)")
                continue

            atr = calculate_atr(candles, period=14)
            # Detect trendlines for this timeframe
            tls = detect_timeframe_trendlines(candles, interval=tf, include_broken=True, max_lines_per_type=2)
            timeframe_lines_map[tf] = tls
            total_lines += len(tls)

            print(f"  📊 [{tf}] Candles: {len(candles)} | ATR: {atr:.4f} | Trendlines: {len(tls)}")

            # Verify each line
            for tl in tls:
                is_res = tl["line_type"] == "resistance_trendline"
                is_sup = tl["line_type"] == "support_trendline"
                p1 = tl["start_point"]
                p2 = tl["end_point"]
                slope = tl["slope"]
                status = tl["status"]
                touches = tl["touch_count"]
                strength = tl["strength"]

                # 1. Coordinate verification
                c_p1 = next((c for c in candles if c["time"] == p1["time"]), None)
                c_p2 = next((c for c in candles if c["time"] == p2["time"]), None)

                if not c_p1:
                    issues.append(f"[{coin} {tf}] P1 timestamp {p1['time']} not found in candle series!")
                else:
                    expected_p1 = c_p1["high"] if is_res else c_p1["low"]
                    if abs(p1["price"] - expected_p1) > 0.01:
                        issues.append(f"[{coin} {tf}] P1 price {p1['price']} doesn't match candle {expected_p1} at {p1['time']}")

                if not c_p2:
                    issues.append(f"[{coin} {tf}] P2 timestamp {p2['time']} not found in candle series!")
                else:
                    expected_p2 = c_p2["high"] if is_res else c_p2["low"]
                    if abs(p2["price"] - expected_p2) > 0.01:
                        issues.append(f"[{coin} {tf}] P2 price {p2['price']} doesn't match candle {expected_p2} at {p2['time']}")

                # 2. Slope verification
                if c_p1 and c_p2:
                    idx1 = candles.index(c_p1)
                    idx2 = candles.index(c_p2)
                    bar_dist = idx2 - idx1
                    if bar_dist > 0:
                        calc_slope = (p2["price"] - p1["price"]) / bar_dist
                        if abs(slope - calc_slope) > 1e-4:
                            issues.append(f"[{coin} {tf}] Slope mismatch! tl.slope={slope}, calc={calc_slope}")

                    # 3. Inter-anchor penetration check
                    for k in range(idx1 + 1, idx2):
                        c_k = candles[k]
                        line_p = p1["price"] + slope * (k - idx1)
                        if is_res:
                            if c_k["close"] > line_p + 0.25 * atr:
                                issues.append(f"[{coin} {tf}] Resistance penetrated between anchors at bar {k}: close {c_k['close']} > line {line_p + 0.25*atr:.2f}")
                        else:
                            if c_k["close"] < line_p - 0.25 * atr:
                                issues.append(f"[{coin} {tf}] Support penetrated between anchors at bar {k}: close {c_k['close']} < line {line_p - 0.25*atr:.2f}")

                    # 4. Status verification
                    # Count closes beyond line
                    breakout_closes = 0
                    wick_pierces_only = 0
                    for k in range(idx2 + 1, len(candles)):
                        c_k = candles[k]
                        line_p = p1["price"] + slope * (k - idx1)
                        if is_res:
                            if c_k["close"] > line_p + 0.25 * atr:
                                breakout_closes += 1
                            elif c_k["high"] > line_p and c_k["close"] <= line_p + 0.25 * atr:
                                wick_pierces_only += 1
                        else:
                            if c_k["close"] < line_p - 0.25 * atr:
                                breakout_closes += 1
                            elif c_k["low"] < line_p and c_k["close"] >= line_p - 0.25 * atr:
                                wick_pierces_only += 1

                    if status == "BROKEN" and breakout_closes < 1:
                        issues.append(f"[{coin} {tf}] False broken flag! Line marked BROKEN but breakout_closes={breakout_closes}, wick_pierces={wick_pierces_only}")

                    if status == "ACTIVE" and breakout_closes >= 2:
                        issues.append(f"[{coin} {tf}] Stale active flag! Line marked ACTIVE but breakout_closes={breakout_closes}")

                print(f"     -> {tl['label']}: {p1['price']} -> {p2['price']} | slope={slope:.4f} | status={status} | touches={touches} | score={strength}")

        # 5. Cross-Timeframe Independence check
        # Verify that coordinates on lower timeframes are not inherited from higher timeframes
        for i in range(len(TIMEFRAMES)):
            tf_i = TIMEFRAMES[i]
            tls_i = timeframe_lines_map.get(tf_i, [])
            for j in range(i + 1, len(TIMEFRAMES)):
                tf_j = TIMEFRAMES[j]
                tls_j = timeframe_lines_map.get(tf_j, [])

                for l1 in tls_i:
                    for l2 in tls_j:
                        # Should not share the same start & end timestamps unless purely accidental (different intervals have different bar times)
                        if l1["start_point"]["time"] == l2["start_point"]["time"] and l1["end_point"]["time"] == l2["end_point"]["time"]:
                            print(f"  ℹ️ [{coin}] Identical anchor times on {tf_i} and {tf_j}: {l1['start_point']['time']} -> {l1['end_point']['time']}")

    await hl_client.close()

    print("\n" + "=" * 80)
    print(f"📋 AUDIT SUMMARY: Total lines tested = {total_lines}")
    print(f"🔍 Total geometric/logical issues detected = {len(issues)}")
    if issues:
        print("\n❌ ISSUES DETECTED:")
        for idx, iss in enumerate(issues[:15], 1):
            print(f"  {idx}. {iss}")
        if len(issues) > 15:
            print(f"  ... and {len(issues) - 15} more issues.")
    else:
        print("✅ ZERO ISSUES! All lines are 100% geometrically and logically sound!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_audit())
