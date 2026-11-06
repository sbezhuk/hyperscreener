import asyncio
from app.analyzer.screener import analyze_coin_data

async def test():
    for tf in ["1d", "4h", "1h", "15m", "5m"]:
        res = await analyze_coin_data("ETH", interval=tf, limit=200)
        sweeps = [s for s in res.get("signals", []) if s.get("category") == "sweep"]
        tls = res.get("liquidity", {}).get("trendlines", [])
        print(f"[{tf.upper()}] Sweeps: {len(sweeps)} | Trendlines: {len(tls)}")
        for sw in sweeps[:1]:
            print("   -> Sweep:", sw.get("title"), ":", sw.get("desc"))
        for tl in tls:
            p1, p2 = tl["p1"]["price"], tl["p2"]["price"]
            print(f"   -> Trendline: {tl.get('label')} ({p1} -> {p2})")

if __name__ == "__main__":
    asyncio.run(test())
