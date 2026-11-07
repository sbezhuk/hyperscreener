import asyncio
from typing import List, Dict, Any
from ..hyperliquid import hl_client
from ..ws_manager import hl_ws_manager
from .levels import analyze_levels
from .mtf_levels import mtf_levels_manager
from .fvg import detect_fvgs
from .mtf_fvg import mtf_fvg_manager
from .liquidity import detect_liquidity_and_sweeps
from .structure import analyze_market_structure

async def analyze_coin_data(
    coin: str,
    interval: str = "5m",
    limit: int = 600,
    include_mtf: bool = True
) -> Dict[str, Any]:
    """
    Performs complete technical & SMC analysis for a single coin strictly for the requested timeframe,
    and optionally calculates independent Multi-Timeframe (MTF) levels across all timeframes.
    """
    candles = await hl_client.get_candles(coin=coin, interval=interval, limit=limit)
    if not candles:
        return {}

    current_price = candles[-1]["close"]
    clean_tf = interval.lower()

    if include_mtf:
        # 1. Multi-Timeframe Levels Engine (Parallel calculation with in-memory caching)
        mtf_levels = await mtf_levels_manager.get_all_timeframe_levels(
            coin=coin,
            current_price=current_price,
            active_interval=interval,
            active_candles=candles
        )
        active_data = mtf_levels.get(clean_tf, {"resistances": [], "supports": []})
        active_res = active_data.get("resistances", [])
        active_sup = active_data.get("supports", [])
    else:
        active_levels = analyze_levels(candles, interval=clean_tf)
        active_res = active_levels.get("resistances", [])
        active_sup = active_levels.get("supports", [])
        mtf_levels = {clean_tf: {"resistances": active_res, "supports": active_sup}}

    cascades = []
    if len(active_res) >= 2:
        r1, r2 = active_res[0], active_res[1]
        c1 = r1.get("center_price", r1.get("price", 0))
        c2 = r2.get("center_price", r2.get("price", 0))
        if c1 > 0:
            diff = (c2 - c1) / c1 * 100
            if diff < 2.5 and r1.get("touches", 0) >= 2:
                cascades.append({
                    "type": "resistance_cascade",
                    "levels": [r1["price"], r2["price"]],
                    "desc": f"Каскад зон опору ({r1['price']}, {r2['price']})",
                    "distPct": r1["distPct"],
                })

    levels_data = {
        "currentPrice": current_price,
        "resistances": active_res,
        "supports": active_sup,
        "cascades": cascades,
    }

    structure_data = analyze_market_structure(candles)
    liquidity_data = detect_liquidity_and_sweeps(candles, interval=interval)

    # 3. FVG Engine (MTF when requested, local fast scan when in screener mode)
    if include_mtf:
        mtf_fvg_results = await mtf_fvg_manager.get_all_timeframe_fvgs(
            coin=coin,
            active_interval=interval,
            active_candles=candles,
            trend=structure_data.get("trend", "NEUTRAL"),
            structure_events=structure_data.get("events", [])
        )
        fvgs = mtf_fvg_results.get("active_fvgs", [])
        all_timeframe_fvgs = mtf_fvg_results.get("all_timeframes", {})
        fvg_confluences = mtf_fvg_results.get("confluences", [])
    else:
        fvgs = detect_fvgs(candles, interval=interval)
        all_timeframe_fvgs = {clean_tf: fvgs}
        fvg_confluences = []

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
        dist_to_gap = abs(current_price - fvg["midpoint_price"]) / current_price * 100
        if dist_to_gap < 3.0 and fvg.get("mitigation_status") != "FULLY MITIGATED":
            is_ifvg = fvg.get("mitigation_status") == "INVERTED"
            f_title = f"{'IFVG' if is_ifvg else 'FVG'} ({'Бичачий' if fvg['type'] == 'BULLISH' else 'Ведмежий'}) [{fvg.get('strength_score', 0)}pts]"
            signals.append({
                "id": f"fvg-{fvg['creation_timestamp']}-{fvg['type']}-{fvg.get('mitigation_status')}",
                "coin": coin,
                "interval": interval,
                "category": "fvg",
                "title": f_title,
                "direction": "LONG" if fvg["type"] == "BULLISH" else "SHORT",
                "desc": f"Зона [{fvg['lower_price']:.4f} - {fvg['upper_price']:.4f}] ({fvg['mitigation_status']}, {fvg.get('mitigation_percent', 0)}% заповн.)",
                "price": fvg["midpoint_price"],
                "distPct": round(dist_to_gap, 2),
                "time": fvg["creation_timestamp"]
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
        "multiTimeframeLevels": mtf_levels,
        "fvgs": fvgs,
        "multiTimeframeFvgs": all_timeframe_fvgs,
        "fvgConfluences": fvg_confluences,
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

    sem = asyncio.Semaphore(4)
    async def fetch_one(coin):
        async with sem:
            await asyncio.sleep(0.05)
            return await analyze_coin_data(coin, interval=interval, limit=120, include_mtf=False)

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
