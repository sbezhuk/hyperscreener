import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.analyzer.screener import analyze_coin_data

COINS = ["BTC", "ETH", "SOL", "PUMP", "MET"]
TIMEFRAMES = ["15m", "1h", "4h"]


async def main():
    print("=" * 100)
    print("PHASE 4: LIVE MARKET VERIFICATION & STRUCTURAL RISK AUDIT")
    print("=" * 100)

    total_lines = 0
    htf_counts = {"ALIGNED": 0, "AGAINST_HTF": 0, "NEUTRAL": 0, "UNAVAILABLE": 0}
    risk_flag_counts = {}

    for coin in COINS:
        print(f"\n--- AUDITING COIN: {coin} ---")
        for tf in TIMEFRAMES:
            try:
                result = await analyze_coin_data(
                    coin=coin,
                    interval=tf,
                    limit=300,
                    include_mtf=True,
                )
            except Exception as e:
                print(f"  [{tf}] Error analyzing {coin}: {e}")
                continue

            mtf_tls = result.get("multiTimeframeTrendlines", {})
            local_tls = mtf_tls.get(tf.lower(), [])
            signals = [s for s in result.get("signals", []) if s.get("category") == "trendline"]

            print(f"  [{tf}] Detected {len(local_tls)} trendline(s):")
            for tl in local_tls:
                total_lines += 1
                q = tl.get("structural_quality")
                state = tl.get("interaction_state")
                htf = tl.get("htf_context", "UNAVAILABLE")
                flags = tl.get("structural_risk_flags", [])
                htf_counts[htf] = htf_counts.get(htf, 0) + 1
                for f in flags:
                    risk_flag_counts[f] = risk_flag_counts.get(f, 0) + 1

                print(f"    * Line {tl['direction']} | Q={q} | State={state} | HTF={htf} | Flags={flags}")

            print(f"  [{tf}] Screener signals for trendlines: {len(signals)}")
            for s in signals:
                print(f"      Signal: {s['title']} | Direction: {s['direction']} | HTF: {s.get('htf_context')} | Flags: {s.get('structural_risk_flags')}")

    print("\n" + "=" * 100)
    print("AGGREGATE STRUCTURAL CONTEXT DISTRIBUTION:")
    print(f"  Total trendlines analyzed: {total_lines}")
    for k, v in htf_counts.items():
        pct = (v / total_lines * 100.0) if total_lines > 0 else 0.0
        print(f"  {k:15}: {v:3} ({pct:5.1f}%)")
    print("\nACTIVE STRUCTURAL RISK FLAGS:")
    for k, v in risk_flag_counts.items():
        print(f"  {k:15}: {v:3}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
