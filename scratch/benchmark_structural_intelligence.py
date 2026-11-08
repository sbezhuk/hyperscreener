import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import detect_timeframe_trendlines
from app.research.pipeline import resolve_research_coins

async def benchmark_performance():
    print("=" * 80)
    print("⚡ PERFORMANCE BENCHMARK: Trendline Structural Intelligence Engine")
    print("=" * 80)

    target_coins = await resolve_research_coins(min_volume_usd=10_000_000, top_n=3)
    for coin in target_coins:
        candles = await hl_client.get_candles(coin=coin, interval="15m", limit=1000)
        if not candles: continue

        # Warm-up run
        _ = detect_timeframe_trendlines(candles, interval="15m", include_broken=True)

        # 50 consecutive runs
        start = time.perf_counter()
        iters = 50
        for _ in range(iters):
            _ = detect_timeframe_trendlines(candles, interval="15m", include_broken=True)
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iters) * 1000.0

        print(f"Asset: {coin:<5} | 1000 candles | 50 iterations | Total: {elapsed*1000:.1f}ms | Avg per cycle: {avg_ms:.2f} ms")

    await hl_client.close()

if __name__ == "__main__":
    asyncio.run(benchmark_performance())
