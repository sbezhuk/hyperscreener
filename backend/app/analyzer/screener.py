import asyncio
from typing import List, Dict, Any
from ..hyperliquid import hl_client
from ..ws_manager import hl_ws_manager
from .levels import analyze_levels
from .fvg import detect_fvgs
from .liquidity import detect_liquidity_and_sweeps
from .structure import analyze_market_structure

async def analyze_coin_data(coin: str, interval: str = "5m", limit: int = 400) -> Dict[str, Any]:
    """
    Performs complete technical & SMC analysis for a single coin strictly for the requested timeframe.
    Each timeframe calculates and maintains its own independent support & resistance levels.
    """
    candles = await hl_client.get_candles(coin=coin, interval=interval, limit=limit)
    if not candles:
        return {}

    current_price = candles[-1]["close"]
    levels_data = analyze_levels(candles, interval=interval)
    fvgs = detect_fvgs(candles, interval=interval)
    liquidity_data = detect_liquidity_and_sweeps(candles, interval=interval)
    structure_data = analyze_market_structure(candles)

    # Compile formations / signals
    signals = []
    
    # 1. False Breakouts / Sweeps (category: "sweep")
    for sweep in liquidity_data["sweeps"]:
        signals.append({
            "id": f"sweep-{sweep['type']}-{sweep['levelPrice']}",
            "coin": coin,
            "interval": interval,
            "category": "sweep",
            "title": sweep["formation"],
            "direction": sweep["direction"],
            "desc": sweep["desc"],
            "price": sweep["levelPrice"],
            "time": sweep["time"]
        })

    # 2. Cascades (category: "cascade")
    for cascade in levels_data["cascades"]:
        signals.append({
            "id": f"cascade-{cascade['levels'][0]}",
            "coin": coin,
            "interval": interval,
            "category": "cascade",
            "title": "Пробій каскаду рівнів",
            "direction": "LONG" if cascade["type"] == "resistance_cascade" else "SHORT",
            "desc": cascade["desc"],
            "price": cascade["levels"][0],
            "distPct": cascade["distPct"],
            "time": candles[-1]["time"]
        })

    # Key level compression approaching (category: "cascade")
    for r in levels_data["resistances"]:
        if r["touches"] >= 2 and 0 < r["distPct"] <= 1.2:
            signals.append({
                "id": f"approach-r-{r['price']}",
                "coin": coin,
                "interval": interval,
                "category": "cascade",
                "title": f"Підтискання до опору x{r['touches']}",
                "direction": "LONG",
                "desc": f"Рівень {r['price']} ({r['distPct']:+.2f}% до рівня) з {r['touches']} дотиками",
                "price": r["price"],
                "distPct": r["distPct"],
                "time": candles[-1]["time"]
            })
            
    for s in levels_data["supports"]:
        if s["touches"] >= 2 and -1.2 <= s["distPct"] < 0:
            signals.append({
                "id": f"approach-s-{s['price']}",
                "coin": coin,
                "interval": interval,
                "category": "cascade",
                "title": f"Підтискання до підтримки x{s['touches']}",
                "direction": "SHORT",
                "desc": f"Рівень {s['price']} ({s['distPct']:+.2f}% до рівня) з {s['touches']} дотиками",
                "price": s["price"],
                "distPct": s["distPct"],
                "time": candles[-1]["time"]
            })

    # 3. Trendlines (category: "trendline")
    for tl in liquidity_data.get("trendlines", []):
        signals.append({
            "id": f"tl-{tl['type']}-{tl['p2']['price']}",
            "coin": coin,
            "interval": interval,
            "category": "trendline",
            "title": tl["label"],
            "direction": "LONG" if "support" in tl["type"] else "SHORT",
            "desc": f"Трендова лінія по свінг-точках ({tl['p1']['price']} -> {tl['p2']['price']})",
            "price": tl["p2"]["price"],
            "time": tl["p2"]["time"]
        })

    # 5. FVG (category: "fvg")
    for fvg in fvgs:
        dist_to_gap = abs(current_price - fvg["mid"]) / current_price * 100
        if dist_to_gap < 2.0:
            signals.append({
                "id": f"fvg-{fvg['startTime']}-{fvg['type']}",
                "coin": coin,
                "interval": interval,
                "category": "fvg",
                "title": f"FVG ({'Бичачий' if fvg['type'] == 'bullish' else 'Ведмежий'})",
                "direction": "LONG" if fvg["type"] == "bullish" else "SHORT",
                "desc": f"Зона дисбалансу [{fvg['bottom']:.4f} - {fvg['top']:.4f}] ({fvg['status']})",
                "price": fvg["mid"],
                "distPct": round(dist_to_gap, 2),
                "time": fvg["startTime"]
            })

    # Register active levels with WS manager for millisecond-level live sweep detection
    hl_ws_manager.update_levels(
        coin=coin,
        interval=interval,
        resistances=levels_data.get("resistances", []),
        supports=levels_data.get("supports", [])
    )

    return {
        "coin": coin,
        "interval": interval,
        "currentPrice": current_price,
        "candles": candles,
        "levels": levels_data,
        "fvgs": fvgs,
        "liquidity": liquidity_data,
        "structure": structure_data,
        "signals": signals
    }


async def scan_market(top_n: int = 25, interval: str = "5m") -> List[Dict[str, Any]]:
    """
    Scans the top N perpetuals on Hyperliquid by 24h volume.
    Limits concurrency to 5 to protect connection pool and API latency.
    """
    coins_meta = await hl_client.get_meta_and_contexts()
    target_coins = [c["name"] for c in coins_meta[:top_n]]

    sem = asyncio.Semaphore(5)
    async def fetch_one(coin):
        async with sem:
            return await analyze_coin_data(coin, interval=interval, limit=120)

    tasks = [fetch_one(coin) for coin in target_coins]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    screener_results = []
    for res in results:
        if isinstance(res, dict) and res.get("signals"):
            screener_results.append({
                "coin": res["coin"],
                "currentPrice": res["currentPrice"],
                "trend": res["structure"]["trend"],
                "signals": res["signals"],
                "signalsCount": len(res["signals"]),
                "resistancesCount": len(res["levels"]["resistances"]),
                "supportsCount": len(res["levels"]["supports"])
            })

    screener_results.sort(key=lambda x: x["signalsCount"], reverse=True)
    return screener_results
