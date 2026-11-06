import asyncio
from app.analyzer.screener import analyze_coin_data

async def main():
    for tf in ["1d", "1h", "5m"]:
        res = await analyze_coin_data("ETH", interval=tf, limit=200)
        levels = res.get("levels", {})
        fvgs = res.get("fvgs", [])
        print(f"\n=== ETH [{tf.upper()}] ===")
        print(f"Resistances (max 3): {len(levels.get('resistances', []))}")
        for r in levels.get("resistances", []):
            print(f"  - Опір: {r['price']} [{r['bottom']}..{r['top']}] x{r['touches']} ({r['distPct']:+.2f}%)")
        print(f"Supports (max 3): {len(levels.get('supports', []))}")
        for s in levels.get("supports", []):
            print(f"  - Підтримка: {s['price']} [{s['bottom']}..{s['top']}] x{s['touches']} ({s['distPct']:+.2f}%)")
        print(f"Clean Fresh FVGs (max 2+2): {len(fvgs)}")
        for f in fvgs:
            print(f"  - FVG {f['type'].upper()} [{f['bottom']}..{f['top']}] (gap: {f['gapPct']}%)")

if __name__ == "__main__":
    asyncio.run(main())
