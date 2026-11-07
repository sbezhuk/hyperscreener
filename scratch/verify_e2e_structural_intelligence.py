import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import detect_timeframe_trendlines
from app.analyzer.mtf_trendline import mtf_trendline_manager
from app.analyzer.screener import analyze_coin_data

TEST_COINS = ["BTC", "ETH", "SOL", "PUMP"]
TEST_TFS = ["15m", "1h", "4h"]

async def run_e2e_verification():
    print("=" * 85)
    print("🚀 E2E VERIFICATION: REAL MARKET CANDLES & STRUCTURAL INTELLIGENCE")
    print("=" * 85)

    total_lines = 0
    state_counts = {}
    q_scores = []

    for coin in TEST_COINS:
        for tf in TEST_TFS:
            candles = await hl_client.get_candles(coin=coin, interval=tf, limit=500)
            if not candles or len(candles) < 30:
                print(f"Skipping {coin} {tf}: insufficient candles")
                continue

            lines = detect_timeframe_trendlines(candles, interval=tf, include_broken=True)
            print(f"\n[{coin} {tf}] Detected {len(lines)} independent trendlines (Candles: {len(candles)})")

            for tl in lines:
                total_lines += 1
                q = tl.get("structural_quality")
                q_scores.append(q)
                state = tl.get("interaction_state")
                state_counts[state] = state_counts.get(state, 0) + 1

                comps = tl.get("structural_quality_components", {})
                p1_p = tl["start_point"]["price"]
                p2_p = tl["end_point"]["price"]
                dist_atr = tl.get("distance_to_line_atr")
                comp_ratio = tl.get("compression_ratio")
                vel = tl.get("arrival_velocity")
                touches = tl.get("touch_count")

                # Strict Contract Assertions
                assert 10.0 <= q <= 98.0, f"Q out of bounds: {q}"
                assert state in ["APPROACHING", "TESTING", "REJECTED", "COMPRESSION", "BREAKOUT", "RETEST", "STALE"], f"Invalid state: {state}"
                assert "anchor_prominence" in comps, "Missing anchor_prominence"
                assert "spacing_regularity" in comps, "Missing spacing_regularity"
                assert "ray_precision" in comps, "Missing ray_precision"
                assert "void_integrity" in comps, "Missing void_integrity"
                assert "structuralQuality" in tl, "Missing camelCase alias"
                assert "interactionState" in tl, "Missing camelCase alias"
                assert "strength" in tl, "Missing legacy strength"
                assert "status" in tl, "Missing legacy status"

                print(f"  • {tl['direction']} ({p1_p} -> {p2_p}) | Q: {q:4.1f} | State: {state:<12} | Touches: x{touches} | Dist: {dist_atr:+.2f} ATR | Comp: {comp_ratio:.2f} | Vel: {vel:+.2f} ATR/b")
                print(f"    Comps: Prom={comps['anchor_prominence']:.1f}, Spacing={comps['spacing_regularity']:.1f}, Prec={comps['ray_precision']:.1f}, Void={comps['void_integrity']:.1f}")

    # Full analysis API pipeline test via analyze_coin_data
    print("\n" + "=" * 85)
    print("Testing full Screener API pipeline (analyze_coin_data) for ETH (15m)...")
    res = await analyze_coin_data("ETH", interval="15m", include_mtf=True)
    active_tls = res.get("trendlines", [])
    mtf_tls = res.get("multiTimeframeTrendlines", {})
    signals = [s for s in res.get("signals", []) if s.get("category") == "trendline"]

    print(f"Active 15m Trendlines: {len(active_tls)}")
    print(f"MTF Trendlines Timeframes: {list(mtf_tls.keys())}")
    print(f"Trendline Signals with Structural Intelligence: {len(signals)}")
    for s in signals:
        assert "structural_quality" in s, "Signal missing structural_quality"
        assert "interaction_state" in s, "Signal missing interaction_state"
        assert "distance_to_line_atr" in s, "Signal missing distance_to_line_atr"
        print(f"  Signal: {s['title']} | Direction: {s['direction']} | Q: {s['structural_quality']} | State: {s['interaction_state']} | Dist: {s['distance_to_line_atr']} ATR")

    await hl_client.close()

    print("\n" + "=" * 85)
    print("E2E SUMMARY:")
    print("=" * 85)
    print(f"Total Trendlines Audited Across Pairs/TFs: {total_lines}")
    if q_scores:
        print(f"Structural Quality (Q) Distribution: Min = {min(q_scores):.1f}, Max = {max(q_scores):.1f}, Mean = {sum(q_scores)/len(q_scores):.1f}")
    print("Market Interaction State Frequencies:")
    for st, cnt in sorted(state_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {st:<15}: {cnt:>3} ({cnt/total_lines*100:5.1f}%)")
    print("\n✅ 100% E2E Contract and State Machine Verification PASSED!")

if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
