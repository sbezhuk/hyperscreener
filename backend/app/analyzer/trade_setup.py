import math
from typing import Dict, List, Any, Optional, Tuple


def _calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculates Average True Range (ATR) from OHLCV candles."""
    if not candles or len(candles) < 2:
        return 0.0
    
    trs: List[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    
    if not trs:
        return 0.0
    
    sample = trs[-period:] if len(trs) >= period else trs
    return sum(sample) / len(sample)


def _round_price(price: float) -> float:
    """Rounds price sensibly depending on magnitude."""
    if price >= 10000:
        return round(price, 1)
    elif price >= 1000:
        return round(price, 2)
    elif price >= 100:
        return round(price, 2)
    elif price >= 10:
        return round(price, 3)
    elif price >= 1:
        return round(price, 4)
    elif price >= 0.1:
        return round(price, 5)
    elif price >= 0.01:
        return round(price, 6)
    else:
        return round(price, 8)


def generate_trade_setup(
    coin: str,
    interval: str,
    current_price: float,
    candles: List[Dict[str, Any]],
    levels: Dict[str, Any],
    fvgs: List[Dict[str, Any]],
    trendlines: List[Dict[str, Any]],
    liquidity: Dict[str, Any],
    structure: Dict[str, Any],
    oi_summary: Optional[Dict[str, Any]] = None,
    signals: Optional[List[Dict[str, Any]]] = None,
    min_rr_threshold: float = 3.0,
    max_risk_pct_limit: float = 3.8,  # Maximum realistic SL risk % for margin trading
) -> Dict[str, Any]:
    """
    Synthesizes technical formations into an actionable, realistic trade setup.
    Enforces professional trading discipline:
      1. POI Proximity: Price must be directly reacting at or near a key level/FVG/sweep/trendline.
      2. Local Realistic Stop Loss: Placed strictly at the local invalidation point (0.8 - 2.5 ATR, max 3.8%).
      3. Obstacle-aware Take Profit: First major opposing level cannot be ignored.
      4. Strict Risk/Reward: Must achieve RR >= 1:3 without jumping through multiple roadblocking barriers.
    """
    if not candles or current_price <= 0:
        return _make_empty_setup(coin, interval, "Недостатньо свічкових даних для аналізу.")

    atr = _calculate_atr(candles, 14)
    if atr <= 0:
        atr = current_price * 0.005  # Fallback: 0.5% price volatility

    trend = (structure.get("trend") or "NEUTRAL").upper()
    resistances = levels.get("resistances", [])
    supports = levels.get("supports", [])
    pivot_points = levels.get("pivot_points", {})
    sweeps = liquidity.get("sweeps", [])
    reg_channel = liquidity.get("regressionChannel") or liquidity.get("regression_channel")

    # 1. Evaluate Long Setup
    long_candidate = _evaluate_long_setup(
        current_price=current_price,
        atr=atr,
        candles=candles,
        supports=supports,
        resistances=resistances,
        pivot_points=pivot_points,
        fvgs=fvgs,
        trendlines=trendlines,
        sweeps=sweeps,
        reg_channel=reg_channel,
        trend=trend,
        oi_summary=oi_summary,
        signals=signals or [],
        min_rr=min_rr_threshold,
        max_risk_pct=max_risk_pct_limit,
    )

    # 2. Evaluate Short Setup
    short_candidate = _evaluate_short_setup(
        current_price=current_price,
        atr=atr,
        candles=candles,
        resistances=resistances,
        supports=supports,
        pivot_points=pivot_points,
        fvgs=fvgs,
        trendlines=trendlines,
        sweeps=sweeps,
        reg_channel=reg_channel,
        trend=trend,
        oi_summary=oi_summary,
        signals=signals or [],
        min_rr=min_rr_threshold,
        max_risk_pct=max_risk_pct_limit,
    )

    # 3. Decision Matrix: Compare Long vs Short
    best_candidate = None
    long_valid = long_candidate.get("is_valid", False)
    short_valid = short_candidate.get("is_valid", False)

    long_score = long_candidate.get("confluence_score", 0)
    short_score = short_candidate.get("confluence_score", 0)

    if long_valid and short_valid:
        if long_score > short_score:
            best_candidate = long_candidate
        elif short_score > long_score:
            best_candidate = short_candidate
        else:
            best_candidate = long_candidate if long_candidate.get("risk_reward", 0) >= short_candidate.get("risk_reward", 0) else short_candidate
    elif long_valid:
        best_candidate = long_candidate
    elif short_valid:
        best_candidate = short_candidate

    # If no candidate passes realistic criteria or minimum score threshold (>= 40)
    if not best_candidate or best_candidate.get("confluence_score", 0) < 40:
        reason_parts = []
        if not long_valid and not short_valid:
            long_rej = long_candidate.get("rejection_reason")
            short_rej = short_candidate.get("rejection_reason")
            if long_rej and short_rej:
                reason_parts.append(f"LONG: {long_rej}. SHORT: {short_rej}.")
            elif long_rej:
                reason_parts.append(long_rej)
            elif short_rej:
                reason_parts.append(short_rej)
            else:
                reason_parts.append("Немає сетапу із співвідношенням Risk/Reward ≥ 1:3 або ціна поза точками входу.")
        elif best_candidate and best_candidate.get("confluence_score", 0) < 40:
            reason_parts.append(
                f"Недостатня сила формацій ({best_candidate.get('confluence_score', 0)}/100 балів). Ринок у невизначеності."
            )
        else:
            reason_parts.append("Ринкові умови не відповідають критеріям безпечного входу з RR ≥ 1:3.")

        return {
            "coin": coin,
            "interval": interval,
            "action": "WAIT",
            "direction": "NEUTRAL",
            "recommendation_title": "ОЧІКУВАННЯ / ПОЗА РИНКОМ",
            "status_label": "НЕМАЄ СЕТАПУ З RR ≥ 1:3",
            "badge_color": "gray",
            "entry_price": None,
            "entry_range": None,
            "stop_loss": None,
            "take_profit": None,
            "targets": [],
            "risk_reward": None,
            "risk_reward_formatted": None,
            "risk_pct": None,
            "reward_pct": None,
            "confluence_score": max(long_score, short_score),
            "confluence_tier": "NONE",
            "confluence_factors": (long_candidate.get("factors") if long_score >= short_score else short_candidate.get("factors")) or [],
            "long_potential": {
                "score": long_score,
                "rr": long_candidate.get("risk_reward"),
                "rejection_reason": long_candidate.get("rejection_reason")
            },
            "short_potential": {
                "score": short_score,
                "rr": short_candidate.get("risk_reward"),
                "rejection_reason": short_candidate.get("rejection_reason")
            },
            "summary_comment": " ".join(reason_parts),
        }

    # Format approved trade signal setup
    direction = best_candidate["direction"]
    entry_p = best_candidate["entry_price"]
    entry_min = best_candidate["entry_range"][0]
    entry_max = best_candidate["entry_range"][1]
    sl_p = best_candidate["stop_loss"]
    tp_p = best_candidate["take_profit"]
    rr_val = best_candidate["risk_reward"]

    risk_pct = round(abs(entry_p - sl_p) / entry_p * 100, 2)
    reward_pct = round(abs(tp_p - entry_p) / entry_p * 100, 2)

    tier = "HIGH" if best_candidate["confluence_score"] >= 75 else ("MEDIUM" if best_candidate["confluence_score"] >= 50 else "SPECULATIVE")

    summary_comment = _build_summary_narrative(
        direction=direction,
        coin=coin,
        entry_price=entry_p,
        entry_range=[entry_min, entry_max],
        sl_price=sl_p,
        tp_price=tp_p,
        rr_val=rr_val,
        risk_pct=risk_pct,
        reward_pct=reward_pct,
        factors=best_candidate["factors"],
    )

    return {
        "coin": coin,
        "interval": interval,
        "action": f"LOOK_FOR_{direction}",
        "direction": direction,
        "recommendation_title": f"ШУКАТИ {direction} ({'ЛОНГ' if direction == 'LONG' else 'ШОРТ'})",
        "status_label": f"АКТИВНИЙ СИГНАЛ (RR 1:{rr_val:.1f})",
        "badge_color": "green" if direction == "LONG" else "red",
        "entry_price": entry_p,
        "entry_range": [entry_min, entry_max],
        "stop_loss": sl_p,
        "take_profit": tp_p,
        "targets": best_candidate.get("targets", [tp_p]),
        "risk_reward": rr_val,
        "risk_reward_formatted": f"1:{rr_val:.1f}",
        "risk_pct": risk_pct,
        "reward_pct": reward_pct,
        "confluence_score": best_candidate["confluence_score"],
        "confluence_tier": tier,
        "confluence_factors": best_candidate["factors"],
        "primary_trigger": best_candidate.get("primary_trigger", "Технічний конфлюенс"),
        "long_potential": {
            "score": long_score,
            "rr": long_candidate.get("risk_reward"),
            "rejection_reason": long_candidate.get("rejection_reason")
        },
        "short_potential": {
            "score": short_score,
            "rr": short_candidate.get("risk_reward"),
            "rejection_reason": short_candidate.get("rejection_reason")
        },
        "summary_comment": summary_comment,
    }


def _evaluate_long_setup(
    current_price: float,
    atr: float,
    candles: List[Dict[str, Any]],
    supports: List[Dict[str, Any]],
    resistances: List[Dict[str, Any]],
    pivot_points: Dict[str, Any],
    fvgs: List[Dict[str, Any]],
    trendlines: List[Dict[str, Any]],
    sweeps: List[Dict[str, Any]],
    reg_channel: Optional[Dict[str, Any]],
    trend: str,
    oi_summary: Optional[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    min_rr: float,
    max_risk_pct: float,
) -> Dict[str, Any]:
    """Evaluates realistic long opportunity with strict local invalidation and obstacle checks."""
    factors: List[Dict[str, Any]] = []
    score = 0
    primary_trigger = ""

    # Recent candle extremes for local stop-loss calculation (last 20 bars)
    recent_candles = candles[-20:] if len(candles) >= 20 else candles
    recent_swing_low = min(float(c["low"]) for c in recent_candles) if recent_candles else current_price - 1.5 * atr

    # 1. Check Bullish Sweeps (Відсік ліквідності знизу)
    bullish_sweeps = [s for s in sweeps if s.get("direction") == "LONG"]
    recent_sweeps = [s for s in bullish_sweeps if (candles[-1]["time"] - s.get("time", 0)) <= 300 * 25]  # Within last 25 bars
    best_sweep = recent_sweeps[-1] if recent_sweeps else None
    if best_sweep:
        oi_conf = bool(best_sweep.get("oiConfirmed") or (best_sweep.get("oiDeltaPct") and best_sweep["oiDeltaPct"] < 0))
        pts = 30 if oi_conf else 20
        score += pts
        primary_trigger = "Зняття ліквідності (Свіп)"
        factors.append({
            "category": "sweep",
            "title": "Зняття ліквідності знизу (Відсік)",
            "desc": f"Свіп на {best_sweep.get('levelPrice')} з відкиданням ціни вгору" + (" (підтверджено спадом OI)" if oi_conf else ""),
            "weight": pts,
        })

    # 2. Check Support Zones strictly close to current price (<= 1.5 * ATR or <= 1.5%)
    valid_supports = []
    for s in supports:
        s_price = float(s.get("price", 0))
        if s_price <= current_price * 1.005:  # Below or right around current price
            dist_atr = abs(current_price - s_price) / max(atr, 1e-6)
            dist_pct = abs(current_price - s_price) / current_price * 100
            if dist_atr <= 2.2 or dist_pct <= 1.8:
                valid_supports.append(s)

    best_sup = None
    if valid_supports:
        valid_supports.sort(key=lambda s: abs(current_price - float(s.get("price", 0))))
        best_sup = valid_supports[0]
        is_strong = (best_sup.get("strength_score", 50) >= 70) or (best_sup.get("touches", 1) >= 3) or (best_sup.get("smc_type") == "ORDER_BLOCK")
        pts = 25 if is_strong else 15
        score += pts
        if not primary_trigger:
            primary_trigger = f"Зона підтримки ({best_sup.get('smc_label', 'Підтримка')})"
        factors.append({
            "category": "level",
            "title": f"Опора на підтримку {best_sup['price']}",
            "desc": f"{best_sup.get('smc_label', 'Підтримка')} (сила: {best_sup.get('strength_score', 60):.0f}), дистанція {(abs(current_price - best_sup['price']) / current_price * 100):.2f}%.",
            "weight": pts,
        })

    # 3. Check Bullish FVG within reaction zone
    bullish_fvgs = [
        f for f in fvgs
        if f.get("type") in ("BULLISH", "bullish") and f.get("mitigation_status") != "FULLY MITIGATED"
    ]
    best_fvg = None
    for f in bullish_fvgs:
        low_p = float(f.get("lower_price", 0))
        high_p = float(f.get("upper_price", 0))
        # Price is inside FVG or within 1.0 ATR above it
        if (low_p <= current_price <= high_p) or (0 <= (current_price - high_p) <= 1.2 * atr):
            best_fvg = f
            pts = 20
            score += pts
            factors.append({
                "category": "fvg",
                "title": f"Бичачий FVG [{_round_price(low_p)} - {_round_price(high_p)}]",
                "desc": f"Зона імбалансу покупців ({f.get('mitigation_status')}, {f.get('mitigation_percent', 0)}% заповн.).",
                "weight": pts,
            })
            break

    # 4. Trendlines
    tl_long_signals = [
        s for s in signals
        if s.get("category") == "trendline" and s.get("direction") == "LONG"
    ]
    if tl_long_signals:
        best_tl = tl_long_signals[0]
        sig_type = best_tl.get("signal_type") or best_tl.get("signalType") or "ACTIVE"
        pts = 25 if (sig_type in ("BREAKOUT", "BOUNCE") or best_tl.get("is_retest")) else 15
        score += pts
        factors.append({
            "category": "trendline",
            "title": best_tl.get("title", "Бичача наклонка"),
            "desc": best_tl.get("desc", "Реакція від трендової лінії або пробій наклонного опору."),
            "weight": pts,
        })
    elif reg_channel and reg_channel.get("channel_position_pct", 50) <= 25:
        score += 15
        factors.append({
            "category": "trendline",
            "title": "Нижня межа тунелю (-2σ)",
            "desc": f"Ціна у зоні перепроданості ({reg_channel.get('channel_position_pct', 0):.0f}% тунелю).",
            "weight": 15,
        })

    # 5. Market Structure Trend
    if trend == "BULLISH":
        score += 20
        factors.append({
            "category": "structure",
            "title": "Бичачий тренд",
            "desc": "Структура ринку у висхідному тренді (HH/HL).",
            "weight": 20,
        })
    elif trend == "NEUTRAL":
        score += 5

    # 6. Open Interest Confirmation
    if oi_summary:
        oi_status = oi_summary.get("oi_status", "NEUTRAL")
        d5 = oi_summary.get("deltas", {}).get("5m", {})
        delta_pct = d5.get("delta_pct", 0) or 0
        if oi_status == "INCREASING" and delta_pct > 0.15:
            score += 15
            factors.append({
                "category": "oi",
                "title": "Набір позицій (+OI)",
                "desc": f"Приплив відкритого інтересу (+{delta_pct:.2f}% за 5хв).",
                "weight": 15,
            })
        elif oi_status == "DECREASING" and delta_pct < -0.3 and best_sweep:
            score += 15
            factors.append({
                "category": "oi",
                "title": "Очищення ліквідності (-OI)",
                "desc": f"Скидання ліквідацій шортів ({delta_pct:.2f}% OI).",
                "weight": 15,
            })

    # PROXIMITY CHECK: Must have at least one concrete trigger near current price
    has_local_trigger = bool(best_sweep or best_sup or best_fvg or tl_long_signals)
    if not has_local_trigger:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "LONG",
            "risk_reward": None,
            "rejection_reason": "Ціна поза зоною вигідного входу (очікуйте відкату до підтримки або FVG)",
        }

    # Determine Entry Price & Range
    entry_price = _round_price(current_price)
    entry_low = _round_price(max(recent_swing_low, current_price - 0.35 * atr))
    entry_high = _round_price(max(current_price, entry_low + 0.1 * atr))
    if entry_low > entry_high:
        entry_low, entry_high = entry_high, entry_low

    # Determine Realistic LOCAL Stop Loss (SL)
    # SL should protect the local structure, NOT an ancient daily level!
    sl_options = [recent_swing_low - 0.25 * atr]
    if best_sweep:
        sw_p = float(best_sweep.get("levelPrice") or current_price)
        if sw_p < current_price:
            sl_options.append(sw_p - 0.25 * atr)
    if best_sup:
        sup_bottom = float(best_sup.get("bottom", best_sup.get("price", current_price)))
        if sup_bottom < current_price:
            sl_options.append(sup_bottom - 0.25 * atr)
    if best_fvg:
        fvg_low = float(best_fvg.get("lower_price", current_price))
        if fvg_low < current_price:
            sl_options.append(fvg_low - 0.2 * atr)

    # We choose the HIGHEST valid structural level strictly below entry (tightest safe invalidation)
    valid_sls = [s for s in sl_options if s < entry_price]
    if not valid_sls:
        valid_sls = [entry_price - 1.2 * atr]

    raw_sl = max(valid_sls)
    
    # Cap maximum risk: cannot exceed max_risk_pct or 3.2 * atr
    max_sl_distance = min(current_price * (max_risk_pct / 100.0), 3.2 * atr)
    if (entry_price - raw_sl) > max_sl_distance:
        if (entry_price - recent_swing_low) <= max_sl_distance and recent_swing_low < entry_price:
            raw_sl = recent_swing_low - 0.2 * atr
        else:
            return {
                "is_valid": False,
                "confluence_score": score,
                "direction": "LONG",
                "risk_reward": None,
                "rejection_reason": f"Неприпустимо великий ризик стопа (>{max_risk_pct}% або >3.2 ATR)",
            }

    sl_price = _round_price(raw_sl)
    risk_amount = entry_price - sl_price
    if risk_amount <= 0:
        return {"is_valid": False, "confluence_score": score, "rejection_reason": "Некоректний розмір ризику для SL"}

    # Search Opposing Barriers / Targets above Entry
    opposing_resistances = []
    for r in resistances:
        r_bottom = float(r.get("bottom", r.get("price", 0)))
        if r_bottom > entry_price:
            opposing_resistances.append(r_bottom)

    for f in fvgs:
        if f.get("type") in ("BEARISH", "bearish") and f.get("mitigation_status") != "FULLY MITIGATED":
            f_low = float(f.get("lower_price", 0))
            if f_low > entry_price:
                opposing_resistances.append(f_low)

    if pivot_points:
        for p_key in ("pp", "r1", "r2", "r3"):
            p_val = float(pivot_points.get(p_key, 0) or 0)
            if p_val > entry_price:
                opposing_resistances.append(p_val)

    opposing_resistances = sorted(list(set(opposing_resistances)))

    if not opposing_resistances:
        if reg_channel and reg_channel.get("slope") is not None:
            N = reg_channel.get("sample_size", 60)
            curr_up = reg_channel["slope"] * (N - 1) + reg_channel["intercept"] + 2.0 * reg_channel["std_dev"]
            if curr_up > entry_price:
                opposing_resistances.append(curr_up)

    if not opposing_resistances:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "LONG",
            "risk_reward": None,
            "rejection_reason": "Немає чітких цільових рівнів опору для фіксації прибутку",
        }

    # CRITICAL OBSTACLE CHECK:
    # The first major resistance cannot be blindly jumped over!
    first_major_obstacle = opposing_resistances[0]
    first_rr = (first_major_obstacle - entry_price) / risk_amount
    first_dist_pct = (first_major_obstacle - entry_price) / entry_price * 100

    # If the first major resistance is right in front of price and offers RR < 2.2,
    # price will likely reject before reaching 1:3!
    if first_rr < 2.2:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "LONG",
            "risk_reward": round(first_rr, 1),
            "rejection_reason": f"Найближчий опір на {_round_price(first_major_obstacle)} (+{first_dist_pct:.1f}%) блокує рух, RR лише 1:{first_rr:.1f} < 1:{min_rr:.1f}",
        }

    # Find the best target among immediate obstacles that satisfies RR >= min_rr
    approved_tp = None
    approved_rr = 0.0
    for target in opposing_resistances:
        reward = target - entry_price
        rr = reward / risk_amount
        if rr >= min_rr:
            approved_tp = _round_price(target)
            approved_rr = round(rr, 1)
            break

    if not approved_tp:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "LONG",
            "risk_reward": round(first_rr, 1),
            "rejection_reason": f"Найближчі рівні опору дають RR 1:{first_rr:.1f} (недостатній запас ходу для 1:{min_rr:.1f})",
        }

    # Final sanity check: Take profit should be realistic (<= 18%)
    reward_pct = (approved_tp - entry_price) / entry_price * 100
    if reward_pct > 18.0:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "LONG",
            "risk_reward": None,
            "rejection_reason": f"Ціль TP зависока (+{reward_pct:.1f}%), немає реалістичного інтрадей-сетапу",
        }

    return {
        "is_valid": True,
        "direction": "LONG",
        "confluence_score": min(score, 100),
        "entry_price": entry_price,
        "entry_range": [entry_low, entry_high],
        "stop_loss": sl_price,
        "take_profit": approved_tp,
        "targets": [approved_tp],
        "risk_reward": approved_rr,
        "factors": factors,
        "primary_trigger": primary_trigger or "Зона інтересу підтримки",
    }


def _evaluate_short_setup(
    current_price: float,
    atr: float,
    candles: List[Dict[str, Any]],
    resistances: List[Dict[str, Any]],
    supports: List[Dict[str, Any]],
    pivot_points: Dict[str, Any],
    fvgs: List[Dict[str, Any]],
    trendlines: List[Dict[str, Any]],
    sweeps: List[Dict[str, Any]],
    reg_channel: Optional[Dict[str, Any]],
    trend: str,
    oi_summary: Optional[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    min_rr: float,
    max_risk_pct: float,
) -> Dict[str, Any]:
    """Evaluates realistic short opportunity with strict local invalidation and obstacle checks."""
    factors: List[Dict[str, Any]] = []
    score = 0
    primary_trigger = ""

    # Recent candle extremes for local stop-loss calculation (last 20 bars)
    recent_candles = candles[-20:] if len(candles) >= 20 else candles
    recent_swing_high = max(float(c["high"]) for c in recent_candles) if recent_candles else current_price + 1.5 * atr

    # 1. Check Bearish Sweeps (Відсік ліквідності зверху)
    bearish_sweeps = [s for s in sweeps if s.get("direction") == "SHORT"]
    recent_sweeps = [s for s in bearish_sweeps if (candles[-1]["time"] - s.get("time", 0)) <= 300 * 25]
    best_sweep = recent_sweeps[-1] if recent_sweeps else None
    if best_sweep:
        oi_conf = bool(best_sweep.get("oiConfirmed") or (best_sweep.get("oiDeltaPct") and best_sweep["oiDeltaPct"] < 0))
        pts = 30 if oi_conf else 20
        score += pts
        primary_trigger = "Зняття ліквідності зверху (Свіп)"
        factors.append({
            "category": "sweep",
            "title": "Зняття ліквідності зверху (Відсік)",
            "desc": f"Свіп на {best_sweep.get('levelPrice')} з відкиданням ціни вниз" + (" (підтверджено спадом OI)" if oi_conf else ""),
            "weight": pts,
        })

    # 2. Check Resistance Zones strictly close to current price (<= 1.5 * ATR or <= 1.5%)
    valid_resistances = []
    for r in resistances:
        r_price = float(r.get("price", 0))
        if r_price >= current_price * 0.995:
            dist_atr = abs(r_price - current_price) / max(atr, 1e-6)
            dist_pct = abs(r_price - current_price) / current_price * 100
            if dist_atr <= 2.2 or dist_pct <= 1.8:
                valid_resistances.append(r)

    best_res = None
    if valid_resistances:
        valid_resistances.sort(key=lambda r: abs(float(r.get("price", 0)) - current_price))
        best_res = valid_resistances[0]
        is_strong = (best_res.get("strength_score", 50) >= 70) or (best_res.get("touches", 1) >= 3) or (best_res.get("smc_type") == "ORDER_BLOCK")
        pts = 25 if is_strong else 15
        score += pts
        if not primary_trigger:
            primary_trigger = f"Зона опору ({best_res.get('smc_label', 'Опір')})"
        factors.append({
            "category": "level",
            "title": f"Реакція на опір {best_res['price']}",
            "desc": f"{best_res.get('smc_label', 'Опір')} (сила: {best_res.get('strength_score', 60):.0f}), дистанція {(abs(best_res['price'] - current_price) / current_price * 100):.2f}%.",
            "weight": pts,
        })

    # 3. Check Bearish FVG within reaction zone
    bearish_fvgs = [
        f for f in fvgs
        if f.get("type") in ("BEARISH", "bearish") and f.get("mitigation_status") != "FULLY MITIGATED"
    ]
    best_fvg = None
    for f in bearish_fvgs:
        low_p = float(f.get("lower_price", 0))
        high_p = float(f.get("upper_price", 0))
        if (low_p <= current_price <= high_p) or (0 <= (low_p - current_price) <= 1.2 * atr):
            best_fvg = f
            pts = 20
            score += pts
            factors.append({
                "category": "fvg",
                "title": f"Ведмежий FVG [{_round_price(low_p)} - {_round_price(high_p)}]",
                "desc": f"Зона імбалансу продавців ({f.get('mitigation_status')}, {f.get('mitigation_percent', 0)}% заповн.).",
                "weight": pts,
            })
            break

    # 4. Trendlines
    tl_short_signals = [
        s for s in signals
        if s.get("category") == "trendline" and s.get("direction") == "SHORT"
    ]
    if tl_short_signals:
        best_tl = tl_short_signals[0]
        sig_type = best_tl.get("signal_type") or best_tl.get("signalType") or "ACTIVE"
        pts = 25 if (sig_type in ("BREAKOUT", "BOUNCE") or best_tl.get("is_retest")) else 15
        score += pts
        factors.append({
            "category": "trendline",
            "title": best_tl.get("title", "Ведмежа наклонка"),
            "desc": best_tl.get("desc", "Відскок від наклонного опору або пробій підтримки."),
            "weight": pts,
        })
    elif reg_channel and reg_channel.get("channel_position_pct", 50) >= 75:
        score += 15
        factors.append({
            "category": "trendline",
            "title": "Стеля тунелю (+2σ)",
            "desc": f"Ціна у зоні перекупленості ({reg_channel.get('channel_position_pct', 0):.0f}% тунелю).",
            "weight": 15,
        })

    # 5. Market Structure Trend
    if trend == "BEARISH":
        score += 20
        factors.append({
            "category": "structure",
            "title": "Ведмежий тренд",
            "desc": "Структура ринку у низхідному тренді (LH/LL).",
            "weight": 20,
        })
    elif trend == "NEUTRAL":
        score += 5

    # 6. Open Interest Confirmation
    if oi_summary:
        oi_status = oi_summary.get("oi_status", "NEUTRAL")
        d5 = oi_summary.get("deltas", {}).get("5m", {})
        delta_pct = d5.get("delta_pct", 0) or 0
        if oi_status == "INCREASING" and delta_pct > 0.15:
            score += 15
            factors.append({
                "category": "oi",
                "title": "Приплив OI за продавцями",
                "desc": f"Зростання відкритого інтересу (+{delta_pct:.2f}% за 5хв).",
                "weight": 15,
            })
        elif oi_status == "DECREASING" and delta_pct < -0.3 and best_sweep:
            score += 15
            factors.append({
                "category": "oi",
                "title": "Каскадний скид лонгів (-OI)",
                "desc": f"Спад відкритого інтересу ({delta_pct:.2f}%).",
                "weight": 15,
            })

    # PROXIMITY CHECK: Must have at least one concrete trigger near current price
    has_local_trigger = bool(best_sweep or best_res or best_fvg or tl_short_signals)
    if not has_local_trigger:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "SHORT",
            "risk_reward": None,
            "rejection_reason": "Ціна поза зоною вигідного входу (очікуйте підходу до опору або FVG)",
        }

    # Determine Entry Price & Range
    entry_price = _round_price(current_price)
    entry_high = _round_price(min(recent_swing_high, current_price + 0.35 * atr))
    entry_low = _round_price(min(current_price, entry_high - 0.1 * atr))
    if entry_low > entry_high:
        entry_low, entry_high = entry_high, entry_low

    # Determine Realistic LOCAL Stop Loss (SL) for SHORT
    sl_options = [recent_swing_high + 0.25 * atr]
    if best_sweep:
        sw_p = float(best_sweep.get("levelPrice") or current_price)
        if sw_p > current_price:
            sl_options.append(sw_p + 0.25 * atr)
    if best_res:
        res_top = float(best_res.get("top", best_res.get("price", current_price)))
        if res_top > current_price:
            sl_options.append(res_top + 0.25 * atr)
    if best_fvg:
        fvg_high = float(best_fvg.get("upper_price", current_price))
        if fvg_high > current_price:
            sl_options.append(fvg_high + 0.2 * atr)

    # We choose the LOWEST valid structural level strictly above entry (tightest safe invalidation)
    valid_sls = [s for s in sl_options if s > entry_price]
    if not valid_sls:
        valid_sls = [entry_price + 1.2 * atr]

    raw_sl = min(valid_sls)

    # Cap maximum risk
    max_sl_distance = min(current_price * (max_risk_pct / 100.0), 3.2 * atr)
    if (raw_sl - entry_price) > max_sl_distance:
        if (recent_swing_high - entry_price) <= max_sl_distance and recent_swing_high > entry_price:
            raw_sl = recent_swing_high + 0.2 * atr
        else:
            return {
                "is_valid": False,
                "confluence_score": score,
                "direction": "SHORT",
                "risk_reward": None,
                "rejection_reason": f"Неприпустимо великий ризик стопа (>{max_risk_pct}% або >3.2 ATR)",
            }

    sl_price = _round_price(raw_sl)
    risk_amount = sl_price - entry_price
    if risk_amount <= 0:
        return {"is_valid": False, "confluence_score": score, "rejection_reason": "Некоректний розмір ризику для SL"}

    # Search Opposing Barriers / Targets below Entry
    opposing_supports = []
    for s in supports:
        s_top = float(s.get("top", s.get("price", 0)))
        if s_top < entry_price:
            opposing_supports.append(s_top)

    for f in fvgs:
        if f.get("type") in ("BULLISH", "bullish") and f.get("mitigation_status") != "FULLY MITIGATED":
            f_high = float(f.get("upper_price", 0))
            if f_high < entry_price:
                opposing_supports.append(f_high)

    if pivot_points:
        for p_key in ("pp", "s1", "s2", "s3"):
            p_val = float(pivot_points.get(p_key, 0) or 0)
            if p_val < entry_price:
                opposing_supports.append(p_val)

    opposing_supports = sorted(list(set(opposing_supports)), reverse=True)

    if not opposing_supports:
        if reg_channel and reg_channel.get("slope") is not None:
            N = reg_channel.get("sample_size", 60)
            curr_low = reg_channel["slope"] * (N - 1) + reg_channel["intercept"] - 2.0 * reg_channel["std_dev"]
            if curr_low < entry_price:
                opposing_supports.append(curr_low)

    if not opposing_supports:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "SHORT",
            "risk_reward": None,
            "rejection_reason": "Немає чітких цільових рівнів підтримки для фіксації прибутку",
        }

    # CRITICAL OBSTACLE CHECK FOR SHORT:
    first_major_obstacle = opposing_supports[0]
    first_rr = (entry_price - first_major_obstacle) / risk_amount
    first_dist_pct = (entry_price - first_major_obstacle) / entry_price * 100

    if first_rr < 2.2:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "SHORT",
            "risk_reward": round(first_rr, 1),
            "rejection_reason": f"Найближча підтримка на {_round_price(first_major_obstacle)} (-{first_dist_pct:.1f}%) блокує рух, RR лише 1:{first_rr:.1f} < 1:{min_rr:.1f}",
        }

    approved_tp = None
    approved_rr = 0.0
    for target in opposing_supports:
        reward = entry_price - target
        rr = reward / risk_amount
        if rr >= min_rr:
            approved_tp = _round_price(target)
            approved_rr = round(rr, 1)
            break

    if not approved_tp:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "SHORT",
            "risk_reward": round(first_rr, 1),
            "rejection_reason": f"Найближчі рівні підтримки дають RR 1:{first_rr:.1f} (недостатній запас ходу для 1:{min_rr:.1f})",
        }

    reward_pct = (entry_price - approved_tp) / entry_price * 100
    if reward_pct > 18.0:
        return {
            "is_valid": False,
            "confluence_score": score,
            "direction": "SHORT",
            "risk_reward": None,
            "rejection_reason": f"Ціль TP занизька (-{reward_pct:.1f}%), немає реалістичного інтрадей-сетапу",
        }

    return {
        "is_valid": True,
        "direction": "SHORT",
        "confluence_score": min(score, 100),
        "entry_price": entry_price,
        "entry_range": [entry_low, entry_high],
        "stop_loss": sl_price,
        "take_profit": approved_tp,
        "targets": [approved_tp],
        "risk_reward": approved_rr,
        "factors": factors,
        "primary_trigger": primary_trigger or "Зона інтересу опору",
    }


def _build_summary_narrative(
    direction: str,
    coin: str,
    entry_price: float,
    entry_range: List[float],
    sl_price: float,
    tp_price: float,
    rr_val: float,
    risk_pct: float,
    reward_pct: float,
    factors: List[Dict[str, Any]],
) -> str:
    """Creates a concise, insightful analytical summary in Ukrainian without repeating raw numbers."""
    dir_ukr = "ЛОНГ (LONG)" if direction == "LONG" else "ШОРТ (SHORT)"
    clean_titles = []
    for f in factors[:2]:
        t = f.get("title", "")
        for prefix in ("Опора на ", "Реакція на ", "Тест "):
            if t.startswith(prefix):
                t = t[len(prefix):]
        clean_titles.append(t)
    factors_text = ", ".join(clean_titles) if clean_titles else "технічний конфлюенс"
    if direction == "LONG":
        return f"Сетап {dir_ukr}: опора на {factors_text}. Локальний стоп надійно захищено структурою, а запас ходу до опору забезпечує співвідношення 1:{rr_val:.1f}."
    else:
        return f"Сетап {dir_ukr}: реакція на {factors_text}. Стоп виставлено за локальним хаєм, а потенціал зниження до підтримки забезпечує співвідношення 1:{rr_val:.1f}."


def _make_empty_setup(coin: str, interval: str, reason: str) -> Dict[str, Any]:
    return {
        "coin": coin,
        "interval": interval,
        "action": "WAIT",
        "direction": "NEUTRAL",
        "recommendation_title": "ОЧІКУВАННЯ / ПОЗА РИНКОМ",
        "status_label": "НЕМАЄ ДАНИХ",
        "badge_color": "gray",
        "entry_price": None,
        "entry_range": None,
        "stop_loss": None,
        "take_profit": None,
        "targets": [],
        "risk_reward": None,
        "risk_reward_formatted": None,
        "risk_pct": None,
        "reward_pct": None,
        "confluence_score": 0,
        "confluence_tier": "NONE",
        "confluence_factors": [],
        "summary_comment": reason,
    }
