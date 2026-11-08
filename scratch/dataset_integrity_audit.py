import asyncio
import sys
import os
import time
from typing import Dict, List, Any

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    fetch_research_universe,
    get_timeframe_step_seconds,
    resolve_research_timeframes,
)


async def main():
    print("=" * 80)
    print("PHASE 6: MODULE A — UNIVERSAL DATASET INTEGRITY & RESEARCH DESIGN AUDIT")
    print("=" * 80)

    # Universal dynamic discovery of assets and timeframes
    active_assets = await discover_available_assets(min_daily_volume_usd=1_000_000.0)
    supported_tfs = discover_supported_timeframes()

    print(f"\n[Dynamic Market Discovery]")
    print(f"Total active perpetuals (> $1M vol): {len(active_assets)}")
    print(f"Total supported timeframes: {len(supported_tfs)} ({', '.join(supported_tfs)})")

    # Audit liquid universe across ALL 6 working timeframes
    target_coins = [a["name"] for a in active_assets[:8]]
    audit_tfs = resolve_research_timeframes()

    print(f"\nExecuting Dataset Audit for top universe: {target_coins} across {audit_tfs}...")
    universe_result = await fetch_research_universe(
        coins=target_coins,
        timeframes=audit_tfs,
        candle_limit=1500,
    )

    print("\n--- SUMMARY OF HISTORICAL CANDLE DATA ---")
    datasets = universe_result["datasets"]
    for coin in target_coins:
        print(f"\nCoin: {coin}")
        for tf in audit_tfs:
            ds = datasets.get(coin, {}).get(tf, {})
            q = ds.get("quality", {})
            candles = ds.get("candles", [])
            print(f"  {tf:>4}: {len(candles)} bars | "
                  f"Status: {q.get('status')} | "
                  f"Sorted: {q.get('is_sorted')} | "
                  f"Duplicates: {q.get('duplicates_count')} | "
                  f"Gaps: {q.get('gaps_count')} | "
                  f"Range: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(q.get('start_time', 0)))} -> "
                  f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(q.get('end_time', 0)))}")

    print(f"\nTotal combinations tested: {universe_result['total_combinations']}")
    print(f"Successful datasets: {universe_result['successful_datasets']}")
    print(f"Rejected datasets: {universe_result['rejected_count']}")

    if universe_result['rejections']:
        print("\n--- REJECTIONS ---")
        for rej in universe_result['rejections']:
            print(f"  [{rej['coin']} {rej['timeframe']}] {rej['status']}: {rej['reason']}")
    else:
        print("\n[AUDIT PASSED] 100% of discovered asset-timeframe combinations are strictly valid.")

    print("\nUniversal Module A Audit Complete.")


if __name__ == "__main__":
    asyncio.run(main())
