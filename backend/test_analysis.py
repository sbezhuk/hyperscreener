import asyncio
from app.analyzer.screener import analyze_coin_data, scan_market

async def test():
    print("=== Testing ETH 5m Analysis ===")
    eth = await analyze_coin_data("ETH", "5m", 200)
    print("Current Price:", eth.get("currentPrice"))
    print("Trend:", eth.get("structure", {}).get("summary"))
    print("Resistances:")
    for r in eth.get("levels", {}).get("resistances", [])[:4]:
        touches_str = f"x{r['touches']}" if r['touches'] > 1 else ""
        print(f"  - Опір {r['price']} {touches_str} ({r['distPct']:+.2f}%)")
    print("Supports:")
    for s in eth.get("levels", {}).get("supports", [])[:4]:
        touches_str = f"x{s['touches']}" if s['touches'] > 1 else ""
        print(f"  - Підтримка {s['price']} {touches_str} ({s['distPct']:+.2f}%)")
    print(f"FVGs found: {len(eth.get('fvgs', []))}")
    for f in eth.get("fvgs", [])[:3]:
        print(f"  - FVG {f['type'].upper()}: [{f['bottom']} - {f['top']}] ({f['status']})")
    
    print("\nSignals for ETH:")
    for sig in eth.get("signals", []):
        print(f"  -> [{sig['direction']}] {sig['title']}: {sig['desc']}")

    print("\n=== Scanning Top 10 Hyperliquid coins for Formations ===")
    scanner = await scan_market(top_n=10, interval="5m")
    print(f"Found {len(scanner)} coins with setups:")
    for item in scanner[:5]:
        coin = item['coin']
        px = item['currentPrice']
        trend = item['trend']
        count = item['signalsCount']
        print(f"\n[{coin}] Ціна: {px} | Тренд: {trend} | Формацій: {count}")
        for s in item['signals'][:3]:
            print(f"   * {s['title']} ({s['direction']}): {s['desc']}")

if __name__ == "__main__":
    asyncio.run(test())
