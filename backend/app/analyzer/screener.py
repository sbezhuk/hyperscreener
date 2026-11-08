import asyncio
from typing import List, Dict, Any, Optional, Tuple
from ..hyperliquid import hl_client
from ..ws_manager import hl_ws_manager
from .oi_tracker import oi_manager
from .levels import analyze_levels
from .mtf_levels import mtf_levels_manager
from .fvg import detect_fvgs
from .mtf_fvg import mtf_fvg_manager
from .liquidity import detect_liquidity_and_sweeps
from .trendline import (
    detect_timeframe_trendlines,
    calculate_atr,
    evaluate_htf_structural_context,
    calculate_linear_regression_channel,
    DEFAULT_COMPRESSION_THRESHOLD,
)
from .mtf_trendline import mtf_trendline_manager, HTF_TIMEFRAME_MAP
from .structure import analyze_market_structure


def _get_trendline_price_at_bar(tl: Dict[str, Any], target_bar_idx: int) -> float:
    """Helper to determine the modeled price of a trendline at target_bar_idx."""
    p1 = tl.get("start_point") or tl.get("p1") or {}
    idx1 = p1.get("index", 0)
    p1_price = float(p1.get("price", 0.0))
    slope = float(tl.get("slope", 0.0))
    if slope != 0.0 or idx1 != 0:
        return p1_price + slope * (target_bar_idx - idx1)
    p2 = tl.get("end_point") or tl.get("p2") or {}
    return float(tl.get("price") or p2.get("price") or p1_price)


def _select_nearest_trendline(
    lines: List[Dict[str, Any]],
    target_price: float,
    curr_bar_idx: int,
    atr: float,
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Deterministically selects the nearest trendline to target_price.
    Tie-breaking hierarchy:
      1. Minimum distance in ATR.
      2. Higher Structural Quality Q.
      3. Newer P2 timestamp.
    Returns: (best_trendline, dist_atr) or None.
    """
    if not lines:
        return None

    scored_lines = []
    for tl in lines:
        lp = _get_trendline_price_at_bar(tl, curr_bar_idx)
        dist_atr = abs(target_price - lp) / max(atr, 1e-6)
        q = float(tl.get("structural_quality", tl.get("strength", 50.0)))
        p2 = tl.get("end_point") or tl.get("p2") or {}
        p2_time = int(p2.get("time", 0))
        scored_lines.append(((dist_atr, -q, -p2_time), tl, dist_atr))

    scored_lines.sort(key=lambda item: item[0])
    best_item = scored_lines[0]
    return best_item[1], best_item[2]


def enrich_signals_with_trendline_context(
    signals: List[Dict[str, Any]],
    active_trendlines: List[Dict[str, Any]],
    candles: List[Dict[str, Any]],
    interval: str,
    coin: Optional[str] = None,
    htf_candles: Optional[List[Dict[str, Any]]] = None,
    atr_period: int = 14,
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    Enriches each signal in-place with descriptive Trendline Structural Context (Phase 5.2).
    Pure enrichment: does not filter, delete, or alter existing signal fields.
    """
    if not signals:
        return signals

    # Fallback template if candles or history are insufficient
    def make_fallback(reason: str) -> Dict[str, Any]:
        return {
            "contextAvailable": False,
            "context_available": False,
            "unavailableReason": reason,
            "unavailable_reason": reason,
            "htfAlignment": "UNAVAILABLE",
            "htf_alignment": "UNAVAILABLE",
            "hasSupportConfluence": False,
            "has_support_confluence": False,
            "confluentLineQ": None,
            "confluent_line_q": None,
            "distanceToSupportAtr": None,
            "distance_to_support_atr": None,
            "distanceToResistanceAtr": None,
            "distance_to_resistance_atr": None,
            "nearestSupportQ": None,
            "nearest_support_q": None,
            "nearestResistanceQ": None,
            "nearest_resistance_q": None,
            "isCompression": False,
            "is_compression": False,
            "compressionRatio": None,
            "compression_ratio": None,
            "isRetest": False,
            "is_retest": False,
            "riskFlags": [],
            "risk_flags": [],
            "structuralTier": "TIER_2_STANDARD",
            "structural_tier": "TIER_2_STANDARD",
        }

    if not candles or len(candles) < max(atr_period, 5):
        fallback = make_fallback("INSUFFICIENT_CANDLES")
        for sig in signals:
            sig["structuralContext"] = fallback
            sig["structural_context"] = fallback
        return signals

    try:
        atr = calculate_atr(candles, atr_period)
        if atr <= 0:
            fallback = make_fallback("INVALID_ATR")
            for sig in signals:
                sig["structuralContext"] = fallback
                sig["structural_context"] = fallback
            return signals

        n_candles = len(candles)
        curr_c = candles[-1]
        curr_price = float(curr_c["close"])
        curr_bar_idx = n_candles - 1

        # Resolve HTF candles strictly from cache if not explicitly provided
        clean_tf = interval.lower()
        if htf_candles is None and coin:
            htf_tf = HTF_TIMEFRAME_MAP.get(clean_tf)
            if htf_tf:
                htf_candles = mtf_trendline_manager.get_cached_candles(coin.upper(), htf_tf)

        # Evaluate HTF market structure context strictly Point-in-Time
        is_closed = bool(curr_c.get("is_closed", True))
        candle_time = int(curr_c.get("time", 0))
        explicit_eval_time = curr_c.get("evaluation_time")

        support_htf_ctx = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=candle_time,
            htf_candles=htf_candles,
            evaluation_time=explicit_eval_time,
            is_candle_closed=is_closed,
            ltf_interval=clean_tf,
        )

        # Volatility Compression
        sub5 = candles[max(0, n_candles - 5):]
        sub20 = candles[max(0, n_candles - 20):]
        a5 = calculate_atr(sub5, 5)
        a20 = calculate_atr(sub20, 20)
        local_comp_ratio = round(a5 / a20, 3) if a20 > 0 else 1.0
        is_local_comp = (local_comp_ratio < compression_threshold)

        # Separate active trendlines
        all_lines = active_trendlines or []
        support_lines = [
            tl for tl in all_lines
            if "support" in tl.get("line_type", tl.get("type", "")) and tl.get("status") != "BROKEN"
        ]
        resistance_lines = [
            tl for tl in all_lines
            if "res" in tl.get("line_type", tl.get("type", "")) and tl.get("status") != "BROKEN"
        ]

        for sig in signals:
            try:
                sig_price = float(sig.get("price") if sig.get("price") is not None else curr_price)
                direction = sig.get("direction", "NEUTRAL")
                category = sig.get("category", "")

                # Deterministic selection
                best_sup_res = _select_nearest_trendline(support_lines, sig_price, curr_bar_idx, atr)
                best_res_res = _select_nearest_trendline(resistance_lines, sig_price, curr_bar_idx, atr)

                # Distance & quality metrics
                if best_sup_res is not None:
                    nearest_sup, sup_dist_atr = best_sup_res
                    distance_to_support_atr = round(sup_dist_atr, 2)
                    nearest_support_q = round(float(nearest_sup.get("structural_quality", nearest_sup.get("strength", 50.0))), 1)
                    sup_comp = (
                        nearest_sup.get("compression_ratio", 1.0) < compression_threshold or
                        nearest_sup.get("interaction_state") == "COMPRESSION"
                    )
                else:
                    nearest_sup = None
                    distance_to_support_atr = None
                    nearest_support_q = None
                    sup_comp = False

                if best_res_res is not None:
                    nearest_res, res_dist_atr = best_res_res
                    distance_to_resistance_atr = round(res_dist_atr, 2)
                    nearest_resistance_q = round(float(nearest_res.get("structural_quality", nearest_res.get("strength", 50.0))), 1)
                    res_comp = (
                        nearest_res.get("compression_ratio", 1.0) < compression_threshold or
                        nearest_res.get("interaction_state") == "COMPRESSION"
                    )
                    res_is_retest = (
                        nearest_res.get("interaction_state") == "RETEST" or
                        nearest_res.get("status") == "RETEST"
                    )
                else:
                    nearest_res = None
                    distance_to_resistance_atr = None
                    nearest_resistance_q = None
                    res_comp = False
                    res_is_retest = False

                # Signal HTF alignment
                if direction == "LONG":
                    htf_alignment = support_htf_ctx
                elif direction == "SHORT":
                    if support_htf_ctx == "ALIGNED":
                        htf_alignment = "AGAINST_HTF"
                    elif support_htf_ctx == "AGAINST_HTF":
                        htf_alignment = "ALIGNED"
                    else:
                        htf_alignment = support_htf_ctx
                else:
                    htf_alignment = "NEUTRAL"

                # Support confluence (LONG Sweep / FVG, Q >= 80, dist <= 0.50 ATR)
                has_support_confluence = False
                confluent_line_q = None
                if direction == "LONG" and distance_to_support_atr is not None and nearest_support_q is not None:
                    if distance_to_support_atr <= 0.50 and nearest_support_q >= 80.0:
                        has_support_confluence = True
                        confluent_line_q = nearest_support_q

                # Compression & Retest
                is_compression = is_local_comp or sup_comp or res_comp
                compression_ratio = local_comp_ratio
                is_retest = res_is_retest or (
                    nearest_sup is not None and (
                        nearest_sup.get("interaction_state") == "RETEST" or
                        nearest_sup.get("status") == "RETEST"
                    )
                )

                # Risk flags
                risk_flags: List[str] = []
                if htf_alignment == "AGAINST_HTF":
                    risk_flags.append("AGAINST_HTF")
                if is_compression:
                    risk_flags.append("COMPRESSION")
                if (nearest_res and (nearest_res.get("interaction_state") == "BREAKOUT" or nearest_res.get("status") == "BROKEN")) or \
                   (nearest_sup and (nearest_sup.get("interaction_state") == "BREAKOUT" or nearest_sup.get("status") == "BROKEN")):
                    risk_flags.append("BREAKOUT")
                if is_retest:
                    risk_flags.append("RETEST")
                if (nearest_res and (nearest_res.get("interaction_state") == "STALE" or nearest_res.get("status") == "STALE")) or \
                   (nearest_sup and (nearest_sup.get("interaction_state") == "STALE" or nearest_sup.get("status") == "STALE")):
                    risk_flags.append("STALE")

                # Classification rules (Phase 5.2):
                # TIER_3_WARNING: AGAINST_HTF or COMPRESSION
                # TIER_1_CONFLUENT: LONG Sweep or FVG, support within 0.50 ATR, Q >= 80
                # TIER_2_STANDARD: default
                if "AGAINST_HTF" in risk_flags or "COMPRESSION" in risk_flags:
                    structural_tier = "TIER_3_WARNING"
                elif has_support_confluence and (category in ["sweep", "fvg"] or direction == "LONG"):
                    structural_tier = "TIER_1_CONFLUENT"
                else:
                    structural_tier = "TIER_2_STANDARD"

                context_dict = {
                    "contextAvailable": True,
                    "context_available": True,
                    "unavailableReason": None,
                    "unavailable_reason": None,
                    "htfAlignment": htf_alignment,
                    "htf_alignment": htf_alignment,
                    "hasSupportConfluence": has_support_confluence,
                    "has_support_confluence": has_support_confluence,
                    "confluentLineQ": confluent_line_q,
                    "confluent_line_q": confluent_line_q,
                    "distanceToSupportAtr": distance_to_support_atr,
                    "distance_to_support_atr": distance_to_support_atr,
                    "distanceToResistanceAtr": distance_to_resistance_atr,
                    "distance_to_resistance_atr": distance_to_resistance_atr,
                    "nearestSupportQ": nearest_support_q,
                    "nearest_support_q": nearest_support_q,
                    "nearestResistanceQ": nearest_resistance_q,
                    "nearest_resistance_q": nearest_resistance_q,
                    "isCompression": is_compression,
                    "is_compression": is_compression,
                    "compressionRatio": compression_ratio,
                    "compression_ratio": compression_ratio,
                    "isRetest": is_retest,
                    "is_retest": is_retest,
                    "riskFlags": risk_flags,
                    "risk_flags": risk_flags,
                    "structuralTier": structural_tier,
                    "structural_tier": structural_tier,
                }
                sig["structuralContext"] = context_dict
                sig["structural_context"] = context_dict
            except Exception as item_err:
                fb = make_fallback(f"SIGNAL_ENRICHMENT_ERROR: {str(item_err)}")
                sig["structuralContext"] = fb
                sig["structural_context"] = fb

    except Exception as main_err:
        fb = make_fallback(f"PIPELINE_ERROR: {str(main_err)}")
        for sig in signals:
            sig["structuralContext"] = fb
            sig["structural_context"] = fb

    return signals

async def analyze_coin_data(
    coin: str,
    interval: str = "5m",
    limit: int = 600,
    include_mtf: bool = True,
    min_oi_drop_pct: Optional[float] = None,
    oi_comparison_bars: Optional[int] = None,
    oi_max_wait_bars: Optional[int] = None,
    only_confirmed_sweeps: bool = False,
) -> Dict[str, Any]:
    """
    Performs complete technical & SMC analysis for a single coin strictly for the requested timeframe,
    and optionally calculates independent Multi-Timeframe (MTF) levels across all timeframes.
    Filters false breakout formations via Open Interest (OI) drop confirmation.
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
        active_data = mtf_levels.get(clean_tf, {"resistances": [], "supports": [], "pivot_points": {}})
        active_res = active_data.get("resistances", [])
        active_sup = active_data.get("supports", [])
        active_pivots = active_data.get("pivot_points", {})
    else:
        active_levels = analyze_levels(candles, interval=clean_tf)
        active_res = active_levels.get("resistances", [])
        active_sup = active_levels.get("supports", [])
        active_pivots = active_levels.get("pivot_points", {})
        mtf_levels = {clean_tf: {"resistances": active_res, "supports": active_sup, "pivot_points": active_pivots}}

    cascades = []
    if len(active_res) >= 2:
        r1, r2 = active_res[0], active_res[1]
        c1 = r1.get("center_price", r1.get("price", 0))
        c2 = r2.get("center_price", r2.get("price", 0))
        if c1 > 0:
            diff = (c2 - c1) / c1 * 100
            if diff < 2.5 and r1.get("touches", 0) >= 1:
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
        "pivot_points": active_pivots,
    }

    structure_data = analyze_market_structure(candles)
    # 3. Independent Multi-Timeframe Trendlines Engine
    if include_mtf:
        mtf_trendlines = await mtf_trendline_manager.get_all_timeframe_trendlines(
            coin=coin,
            active_interval=interval,
            active_candles=candles,
        )
        active_tls = mtf_trendlines.get(clean_tf, [])
    else:
        active_tls = detect_timeframe_trendlines(candles, interval=clean_tf)
        mtf_trendlines = {clean_tf: active_tls}

    # Pass confirmed active resistance and support levels to false breakout detector with OI tracker
    all_levels = active_res + active_sup
    coin_tracker = oi_manager.get_tracker(coin)
    liquidity_data = detect_liquidity_and_sweeps(
        candles,
        interval=interval,
        levels=all_levels,
        oi_tracker=coin_tracker,
        coin=coin,
        min_oi_drop_pct=min_oi_drop_pct,
        only_confirmed=only_confirmed_sweeps,
    )
    # Ensure active timeframe trendlines are synced
    liquidity_data["trendlines"] = active_tls

    # 3.1 Linear Regression Channel Engine (OLS: y = kx + b)
    regression_channel = calculate_linear_regression_channel(
        candles=candles,
        interval=clean_tf,
        lookback=60,
        num_std=2.0
    )
    liquidity_data["regressionChannel"] = regression_channel
    liquidity_data["regression_channel"] = regression_channel

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
    
    # 1. False Breakouts / Sweeps (category: "sweep") with full OI confirmation metadata
    for sweep in liquidity_data["sweeps"]:
        signals.append({
            "id": sweep.get("id") or f"sweep-{sweep['type']}-{sweep['levelPrice']}-{sweep['time']}",
            "coin": coin,
            "interval": interval,
            "category": "sweep",
            "title": sweep["formation"],
            "direction": sweep["direction"],
            "desc": sweep["desc"],
            "price": sweep["levelPrice"],
            "time": sweep["time"],
            "confirmationTime": sweep.get("confirmationTime", sweep["time"]),
            "subType": sweep.get("subType", "wick_rejection"),
            "touches": sweep.get("touches", 1),
            "levelStrength": sweep.get("levelStrength", 50.0),
            "confirmationStatus": sweep.get("confirmationStatus", "UNCONFIRMED"),
            "statusLabel": sweep.get("statusLabel"),
            "oiConfirmed": sweep.get("oiConfirmed", False),
            "oiDeltaPct": sweep.get("oiDeltaPct"),
            "oiDelta": sweep.get("oiDelta"),
            "oiReason": sweep.get("oiReason"),
            "oiReasonDesc": sweep.get("oiReasonDesc"),
            "badgeColor": "green" if sweep.get("oiConfirmed") else ("blue" if sweep.get("confirmationStatus") == "POTENTIAL" else "gray"),
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

    # 3. Trendlines (category: "trendline"): Distinct Breakout (with Retest) and Bounce Signals with OI confirmation
    oi_5m = coin_tracker.compute_interval_delta(300) if coin_tracker else {}
    oi_delta_pct = oi_5m.get("delta_pct") if oi_5m.get("is_valid") else None
    oi_delta_val = oi_5m.get("delta") if oi_5m.get("is_valid") else None
    oi_thresh = coin_tracker.compute_oi_volatility() if coin_tracker else 0.5

    for tl in active_tls:
        p1_price = tl.get("start_point", {}).get("price", tl.get("p1", {}).get("price"))
        p2_price = tl.get("end_point", {}).get("price", tl.get("p2", {}).get("price"))
        p2_time = tl.get("end_point", {}).get("time", tl.get("p2", {}).get("time"))
        line_type = tl.get("line_type", tl.get("type", ""))
        is_res = "resistance" in line_type or "res" in line_type
        label_side = "Опір" if is_res else "Підтримка"
        touch_count = tl.get("touch_count", tl.get("touches", 2))
        is_confirmed = tl.get("is_confirmed", touch_count >= 3)
        interaction_state = tl.get("interaction_state", tl.get("interactionState", "ACTIVE"))
        status = tl.get("status", "ACTIVE")
        dist_atr = tl.get("distance_to_line_atr", tl.get("distanceToLineAtr", 0.0))

        is_breakout = (status == "BROKEN" or interaction_state in ("BREAKOUT", "RETEST"))
        is_retest = (interaction_state == "RETEST")

        if is_breakout:
            signal_type = "BREAKOUT"
            direction = "LONG" if is_res else "SHORT"
            if is_retest:
                title = f"Пробій з ретестом наклонної ({label_side})"
                desc = f"Підтверджений ретест пробитої наклонної ({p1_price} -> {p2_price}) [{clean_tf}]."
            else:
                title = f"Пробій наклонної ({label_side})"
                desc = f"Імпульсний пробій наклонної лінії ({p1_price} -> {p2_price}) [{clean_tf}]."

            if oi_delta_pct is not None and oi_delta_pct > oi_thresh:
                oi_confirmed = True
                status_label = "ІСТИННИЙ ПРОБІЙ (+OI)"
                badge_color = "green"
                oi_reason = f"Зростання відкритого інтересу (+{oi_delta_pct:.2f}%) підтверджує набір позицій за пробоєм"
            elif oi_delta_pct is not None and oi_delta_pct < -oi_thresh:
                oi_confirmed = False
                status_label = "ПРОБІЙ НА СКВІЗІ (-OI)"
                badge_color = "red"
                oi_reason = f"Спад відкритого інтересу ({oi_delta_pct:.2f}%) свідчить про закриття позицій (ризик хибного пробою)"
            else:
                oi_confirmed = False
                status_label = "ПРОБІЙ (НЕЙТР. OI)"
                badge_color = "blue"
                oi_reason = f"Пробій без істотної зміни OI ({oi_delta_pct:+.2f}%)" if oi_delta_pct is not None else "Дані OI відсутні"

        elif abs(dist_atr) <= 0.45 and interaction_state in ("TESTING", "REJECTED", "COMPRESSION"):
            signal_type = "BOUNCE"
            direction = "LONG" if not is_res else "SHORT"
            conf_tag = f" x{touch_count}" + (" [Підтверджена 3+]" if is_confirmed else "")
            title = f"Відскок від наклонної ({label_side}){conf_tag}"
            desc = f"Реакція відскоку ціни від наклонної лінії ({p1_price} -> {p2_price}) [{clean_tf}]."

            if oi_delta_pct is not None and oi_delta_pct > 0.05:
                oi_confirmed = True
                status_label = "ВІДСКОК + НАБІР OI"
                badge_color = "green"
                oi_reason = f"Набір позицій (+{oi_delta_pct:.2f}% OI) на тесті та утриманні лінії"
            else:
                oi_confirmed = False
                status_label = "ВІДСКОК ВІД НАКЛОННОЇ"
                badge_color = "blue"
                oi_reason = "Відштовхування ціни від лінії без вираженого накопичення OI"

        else:
            signal_type = "APPROACH"
            direction = "LONG" if not is_res else "SHORT"
            title = tl.get("timeframe_label", tl.get("label", f"Наклонка ({label_side})"))
            desc = f"Трендова лінія по свінг-точках ({p1_price} -> {p2_price}) [{clean_tf}]"
            oi_confirmed = False
            status_label = "АКТИВНА НАКЛОНКА"
            badge_color = "gray"
            oi_reason = f"Дистанція до лінії: {dist_atr:.2f} ATR"

        signals.append({
            "id": tl.get("id") or f"tl-{clean_tf}-{tl['line_type']}-{p2_price}",
            "coin": coin,
            "interval": interval,
            "category": "trendline",
            "signal_type": signal_type,
            "signalType": signal_type,
            "is_retest": is_retest,
            "isRetest": is_retest,
            "is_confirmed": is_confirmed,
            "isConfirmed": is_confirmed,
            "title": title,
            "direction": direction,
            "desc": desc,
            "price": p2_price,
            "time": p2_time,
            "strength": tl.get("structural_quality", tl.get("strength", 50.0)),
            "status": status,
            "statusLabel": status_label,
            "status_label": status_label,
            "badgeColor": badge_color,
            "badge_color": badge_color,
            "oiConfirmed": oi_confirmed,
            "oi_confirmed": oi_confirmed,
            "oiDeltaPct": oi_delta_pct,
            "oi_delta_pct": oi_delta_pct,
            "oiDelta": oi_delta_val,
            "oi_delta": oi_delta_val,
            "oiReason": oi_reason,
            "oi_reason": oi_reason,
            "structural_quality": tl.get("structural_quality", 50.0),
            "interaction_state": interaction_state,
            "structuralQuality": tl.get("structural_quality", 50.0),
            "interactionState": interaction_state,
            "touch_count": touch_count,
            "touchCount": touch_count,
            "distance_to_line_atr": dist_atr,
            "distanceToLineAtr": dist_atr,
            "compression_ratio": tl.get("compression_ratio", 1.0),
            "compressionRatio": tl.get("compression_ratio", 1.0),
            "htf_context": tl.get("htf_context", "UNAVAILABLE"),
            "htfContext": tl.get("htf_context", "UNAVAILABLE"),
            "structural_risk_flags": tl.get("structural_risk_flags", []),
            "structuralRiskFlags": tl.get("structural_risk_flags", []),
        })

    # 3.1 Linear Regression Trend Channel Signals
    if regression_channel and regression_channel.get("r_squared", 0.0) >= 0.35 and len(candles) >= 15:
        curr_c = candles[-1]
        prev_c = candles[-2] if len(candles) >= 2 else curr_c
        N_chan = regression_channel.get("sample_size", 60)
        k_slope = regression_channel["slope"]
        b_intercept = regression_channel["intercept"]
        sigma = regression_channel["std_dev"]
        num_std = regression_channel.get("num_std", 2.0)

        curr_mid = k_slope * (N_chan - 1) + b_intercept
        curr_up = curr_mid + num_std * sigma
        curr_low = curr_mid - num_std * sigma

        prev_mid = k_slope * (N_chan - 2) + b_intercept
        prev_up = prev_mid + num_std * sigma
        prev_low = prev_mid - num_std * sigma

        pos_pct = regression_channel.get("channel_position_pct", 50.0)
        r2_val = regression_channel.get("r_squared", 0.0)

        chan_sig = None

        # Scenario 1: False Breakout of Channel (Wick outside boundary + close inside)
        if (curr_c["high"] > curr_up and curr_c["close"] <= curr_up) or (prev_c["high"] > prev_up and curr_c["close"] < curr_up and curr_c["close"] <= prev_c["close"]):
            chan_sig = {
                "id": f"regchan-fbreak-up-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_FALSE_BREAKOUT",
                "signalType": "CHANNEL_FALSE_BREAKOUT",
                "direction": "SHORT",
                "title": f"Хибний пробій стелі тунелю (+2σ) [R²: {r2_val}]",
                "desc": f"Свічка виходила за верхню межу тунелю ({curr_up:.4f}), але закрилася всередині. Сигнал повернення до медіани ({curr_mid:.4f}).",
                "price": round(curr_up, 4),
                "target_price": round(curr_mid, 4),
                "time": curr_c["time"],
                "status": "ACTIVE",
                "statusLabel": "ХИБНИЙ ПРОБІЙ СТЕЛІ",
                "status_label": "ХИБНИЙ ПРОБІЙ СТЕЛІ",
                "badgeColor": "red",
                "badge_color": "red",
                "oiConfirmed": bool(oi_delta_pct and oi_delta_pct < 0),
                "oi_confirmed": bool(oi_delta_pct and oi_delta_pct < 0),
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": "Зняття ліквідності над тунелем із поверненням всередину",
                "strength": int(r2_val * 100),
            }
        elif (curr_c["low"] < curr_low and curr_c["close"] >= curr_low) or (prev_c["low"] < prev_low and curr_c["close"] > curr_low and curr_c["close"] >= prev_c["close"]):
            chan_sig = {
                "id": f"regchan-fbreak-low-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_FALSE_BREAKOUT",
                "signalType": "CHANNEL_FALSE_BREAKOUT",
                "direction": "LONG",
                "title": f"Хибний пробій дна тунелю (-2σ) [R²: {r2_val}]",
                "desc": f"Свічка виходила за нижню межу тунелю ({curr_low:.4f}), але закрилася всередині. Сигнал повернення до медіани ({curr_mid:.4f}).",
                "price": round(curr_low, 4),
                "target_price": round(curr_mid, 4),
                "time": curr_c["time"],
                "status": "ACTIVE",
                "statusLabel": "ХИБНИЙ ПРОБІЙ ДНА",
                "status_label": "ХИБНИЙ ПРОБІЙ ДНА",
                "badgeColor": "green",
                "badge_color": "green",
                "oiConfirmed": bool(oi_delta_pct and oi_delta_pct < 0),
                "oi_confirmed": bool(oi_delta_pct and oi_delta_pct < 0),
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": "Зняття ліквідності під тунелем із поверненням всередину",
                "strength": int(r2_val * 100),
            }

        # Scenario 2: Channel Breakout (Close strictly outside tunnel)
        elif curr_c["close"] > curr_up:
            oi_conf = bool(oi_delta_pct and oi_delta_pct > oi_thresh)
            chan_sig = {
                "id": f"regchan-break-up-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_BREAKOUT",
                "signalType": "CHANNEL_BREAKOUT",
                "direction": "LONG",
                "title": f"Пробій тунелю тренду вгору (+2σ) [R²: {r2_val}]",
                "desc": f"Ціна закрилася вище верхньої межі тунелю ({curr_up:.4f}). Імпульсний вихід з тренду.",
                "price": round(curr_up, 4),
                "time": curr_c["time"],
                "status": "BROKEN",
                "statusLabel": "ІСТИННИЙ ПРОБІЙ ТУНЕЛЮ (+OI)" if oi_conf else "ПРОБІЙ ТУНЕЛЮ ВГОРУ",
                "status_label": "ІСТИННИЙ ПРОБІЙ ТУНЕЛЮ (+OI)" if oi_conf else "ПРОБІЙ ТУНЕЛЮ ВГОРУ",
                "badgeColor": "green" if oi_conf else "blue",
                "badge_color": "green" if oi_conf else "blue",
                "oiConfirmed": oi_conf,
                "oi_confirmed": oi_conf,
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": f"Вихід з тунелю з динамікою OI: {oi_delta_pct:+.2f}%" if oi_delta_pct else "Вихід за межі 2σ",
                "strength": int(r2_val * 100),
            }
        elif curr_c["close"] < curr_low:
            oi_conf = bool(oi_delta_pct and oi_delta_pct > oi_thresh)
            chan_sig = {
                "id": f"regchan-break-low-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_BREAKOUT",
                "signalType": "CHANNEL_BREAKOUT",
                "direction": "SHORT",
                "title": f"Пробій тунелю тренду вниз (-2σ) [R²: {r2_val}]",
                "desc": f"Ціна закрилася нижче нижньої межі тунелю ({curr_low:.4f}). Прискорення падіння.",
                "price": round(curr_low, 4),
                "time": curr_c["time"],
                "status": "BROKEN",
                "statusLabel": "ІСТИННИЙ ПРОБІЙ ТУНЕЛЮ (+OI)" if oi_conf else "ПРОБІЙ ТУНЕЛЮ ВНИЗ",
                "status_label": "ІСТИННИЙ ПРОБІЙ ТУНЕЛЮ (+OI)" if oi_conf else "ПРОБІЙ ТУНЕЛЮ ВНИЗ",
                "badgeColor": "red" if oi_conf else "blue",
                "badge_color": "red" if oi_conf else "blue",
                "oiConfirmed": oi_conf,
                "oi_confirmed": oi_conf,
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": f"Пробій нижньої межі з динамікою OI: {oi_delta_pct:+.2f}%" if oi_delta_pct else "Вихід під межу -2σ",
                "strength": int(r2_val * 100),
            }

        # Scenario 3: Boundary Test / Overbought / Oversold
        elif pos_pct >= 85.0:
            chan_sig = {
                "id": f"regchan-test-up-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_TEST",
                "signalType": "CHANNEL_TEST",
                "direction": "SHORT",
                "title": f"Тест стелі тунелю (Перекупленість) [R²: {r2_val}]",
                "desc": f"Ціна на {pos_pct:.0f}% висоти тунелю біля верхньої межі ({curr_up:.4f}). Ціль: медіана ({curr_mid:.4f}).",
                "price": round(curr_up, 4),
                "target_price": round(curr_mid, 4),
                "time": curr_c["time"],
                "status": "ACTIVE",
                "statusLabel": "СТЕЛЯ ТУНЕЛЮ (85%+)",
                "status_label": "СТЕЛЯ ТУНЕЛЮ (85%+)",
                "badgeColor": "amber",
                "badge_color": "amber",
                "oiConfirmed": False,
                "oi_confirmed": False,
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": "Зона перекупленості тунелю, потенціал відкату до медіани",
                "strength": int(r2_val * 90),
            }
        elif pos_pct <= 15.0:
            chan_sig = {
                "id": f"regchan-test-low-{curr_c['time']}",
                "coin": coin,
                "interval": interval,
                "category": "trendline",
                "signal_type": "CHANNEL_TEST",
                "signalType": "CHANNEL_TEST",
                "direction": "LONG",
                "title": f"Тест дна тунелю (Перепроданість) [R²: {r2_val}]",
                "desc": f"Ціна на {pos_pct:.0f}% висоти тунелю біля нижньої межі ({curr_low:.4f}). Ціль: медіана ({curr_mid:.4f}).",
                "price": round(curr_low, 4),
                "target_price": round(curr_mid, 4),
                "time": curr_c["time"],
                "status": "ACTIVE",
                "statusLabel": "ДНО ТУНЕЛЮ (15%-)",
                "status_label": "ДНО ТУНЕЛЮ (15%-)",
                "badgeColor": "blue",
                "badge_color": "blue",
                "oiConfirmed": False,
                "oi_confirmed": False,
                "oiDeltaPct": oi_delta_pct,
                "oi_delta_pct": oi_delta_pct,
                "oiReason": "Зона перепроданості тунелю, потенціал відскоку до медіани",
                "strength": int(r2_val * 90),
            }

        if chan_sig:
            signals.insert(0, chan_sig)

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

    # 6. Open Interest (OI) Analysis & Level Breakout Confirmation
    active_all_levels = levels_data.get("resistances", []) + levels_data.get("supports", [])
    oi_summary = oi_manager.get_coin_oi_summary(coin=coin, levels=active_all_levels)

    for bs in oi_summary.get("breakout_signals", []):
        event_time = int(bs.get("test_start_time") or bs.get("current_time", 0))
        signals.append({
            "id": f"oi-{bs['level_id']}-{event_time}",
            "coin": coin,
            "interval": interval,
            "category": "sweep" if bs.get("scenario") in ["SCENARIO_B"] else "cascade",
            "title": bs["status"],
            "direction": "LONG" if bs["direction"] == "UP" else "SHORT",
            "desc": bs["interpretation"],
            "price": bs["breakout_price"] or bs["current_price"],
            "distPct": round(bs.get("oi_delta_pct") or 0.0, 2),
            "time": event_time,
            "scenario": bs.get("scenario"),
            "badgeColor": bs.get("badge_color")
        })

    # 7. Enrich signals with Trendline Structural Context (Phase 5.2)
    signals = enrich_signals_with_trendline_context(
        signals=signals,
        active_trendlines=active_tls,
        candles=candles,
        interval=interval,
        coin=coin,
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
        "trendlines": active_tls,
        "multiTimeframeTrendlines": mtf_trendlines,
        "regressionChannel": regression_channel,
        "regression_channel": regression_channel,
        "liquidity": liquidity_data,
        "structure": structure_data,
        "signals": signals,
        "oi": oi_summary
    }


async def scan_market(
    top_n: int = 25,
    interval: str = "5m",
    min_oi_drop_pct: Optional[float] = None,
    only_confirmed_sweeps: bool = False,
) -> List[Dict[str, Any]]:
    """
    Scans the top N perpetuals on Hyperliquid by 24h volume.
    Limits concurrency to 4 to protect connection pool and API latency.
    """
    coins_meta = await hl_client.get_meta_and_contexts()
    target_coins = [c["name"] for c in coins_meta[:top_n]]

    # Sync monitored coins so newly listed perpetuals are tracked
    if coins_meta:
        asyncio.create_task(hl_ws_manager.update_monitored_coins([c["name"] for c in coins_meta]))

    sem = asyncio.Semaphore(4)
    async def fetch_one(coin):
        async with sem:
            await asyncio.sleep(0.05)
            return await analyze_coin_data(
                coin,
                interval=interval,
                limit=120,
                include_mtf=False,
                min_oi_drop_pct=min_oi_drop_pct,
                only_confirmed_sweeps=only_confirmed_sweeps,
            )

    tasks = [fetch_one(coin) for coin in target_coins]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    screener_results = []
    for res in results:
        if isinstance(res, dict) and res.get("signals"):
            oi_info = res.get("oi", {})
            d5 = oi_info.get("deltas", {}).get("5m", {})
            screener_results.append({
                "coin": res["coin"],
                "currentPrice": res["currentPrice"],
                "trend": res["structure"]["trend"],
                "signals": res["signals"],
                "signalsCount": len(res["signals"]),
                "resistancesCount": len(res["levels"]["resistances"]),
                "supportsCount": len(res["levels"]["supports"]),
                "openInterest": oi_info.get("current_oi", 0.0),
                "oiDelta5m": d5.get("delta", 0.0),
                "oiDeltaPct5m": d5.get("delta_pct", 0.0),
                "oiStatus": oi_info.get("oi_status", "NEUTRAL"),
                "oiColor": oi_info.get("oi_color", "gray"),
                "oiDeltaStatus5m": d5.get("status", "OK"),
                "oiThresholdPct": oi_info.get("volatility_threshold_pct", 0.25)
            })

    screener_results.sort(key=lambda x: x["signalsCount"], reverse=True)
    return screener_results
