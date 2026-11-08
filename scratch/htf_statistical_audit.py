import asyncio
import sys
import os
import math
from collections import defaultdict
from typing import List, Dict, Any, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    calculate_atr,
    find_swings_for_trendlines,
    evaluate_htf_structural_context,
    compute_structural_risk_flags,
    TIMEFRAME_SWING_CONFIG,
    DEFAULT_COMPRESSION_THRESHOLD,
)
from app.analyzer.structure import analyze_market_structure
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
)

TIMEFRAME_PAIRS = [
    ("15m", "1h"),
    ("1h", "4h"),
    ("4h", "1d"),
]
HORIZON = 15


def wilson_score_ci(successes: int, total: int, z: float = 1.96) -> Tuple[float, float, float]:
    """Calculates Wilson score 95% confidence interval for a binomial proportion."""
    if total == 0:
        return 0.0, 0.0, 0.0
    p_hat = successes / total
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) + (z**2) / (4.0 * total)) / total)) / denom
    ci_low = max(0.0, center - margin)
    ci_high = min(1.0, center + margin)
    return p_hat, ci_low, ci_high


def pit_htf_filter(htf_candles: List[Dict[str, Any]], ltf_candle_time: int, ltf_step: int, strict_closed: bool = True) -> List[Dict[str, Any]]:
    """
    Point-in-Time filter:
    If strict_closed is True, an HTF candle is included ONLY if it is fully closed at or before ltf_candle_time + ltf_step.
    """
    if not htf_candles or len(htf_candles) < 2:
        return []
    htf_step = htf_candles[1]["time"] - htf_candles[0]["time"]
    
    if strict_closed:
        # Candle close time must be <= LTF bar close time
        ltf_close = ltf_candle_time + ltf_step
        return [c for c in htf_candles if c["time"] + htf_step <= ltf_close]
    else:
        # Flawed condition that includes unclosed candle
        return [c for c in htf_candles if c["time"] <= ltf_candle_time]


async def run_statistical_audit():
    print("=" * 100)
    print("PHASE 4.5: INDEPENDENT STATISTICAL AUDIT & LARGE-SAMPLE WALK-FORWARD SCAN")
    print("=" * 100)

    # Dictionary to aggregate results per (coin, ltf)
    dataset_stats = defaultdict(lambda: {
        "total_lines": 0,
        "aligned": 0,
        "against_htf": 0,
        "neutral": 0,
        "unavailable": 0,
        "compression": 0,
        "breakout": 0,
        "stale": 0,
        "against_htf_breakouts": 0,
        "aligned_breakouts": 0,
        "compression_breakouts": 0,
        "q_values": [],
    })

    # Step duration in seconds
    tf_seconds = {
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }

    grand_total_lines = 0

    target_coins = await resolve_research_coins(min_volume_usd=5_000_000, top_n=8)
    print(f"Universally discovered assets: {target_coins}")

    for coin in target_coins:
        print(f"\nProcessing {coin} historical datasets...")
        for ltf, htf in TIMEFRAME_PAIRS:
            ltf_step = tf_seconds[ltf]
            htf_step = tf_seconds[htf]

            ds_ltf = await get_single_dataset(coin=coin, timeframe=ltf, limit=1000)
            ds_htf = await get_single_dataset(coin=coin, timeframe=htf, limit=500)
            c_ltf = ds_ltf["candles"]
            c_htf = ds_htf["candles"]

            if not c_ltf or len(c_ltf) < 80 or not c_htf or len(c_htf) < 30:
                print(f"  [{coin} {ltf}->{htf}] Insufficient candle history.")
                continue

            n_ltf = len(c_ltf)
            stats_key = f"{coin}_{ltf}"

            # Walk-forward Point-in-Time bar-by-bar
            # Sample every 5 bars to reduce autocorrelation while preserving independent events
            for t_idx in range(50, n_ltf - HORIZON, 5):
                curr_c = c_ltf[t_idx]
                curr_time = curr_c["time"]
                candles_to_t = c_ltf[:t_idx + 1]

                atr = calculate_atr(candles_to_t, 14)
                if atr <= 0:
                    continue

                # Filter HTF point-in-time (strictly closed)
                pit_htf = [c for c in c_htf if c["time"] + htf_step <= curr_time + ltf_step]
                if len(pit_htf) < 20:
                    continue

                htf_struct = analyze_market_structure(pit_htf)
                htf_trend = htf_struct.get("trend", "NEUTRAL")

                # Detect swings up to t
                swings = find_swings_for_trendlines(candles_to_t, interval=ltf, atr=atr)
                highs = swings["highs"][-6:]
                lows = swings["lows"][-6:]

                # 1. Evaluate resistance lines
                for i in range(len(highs) - 1):
                    for j in range(i + 1, len(highs)):
                        p1, p2 = highs[i], highs[j]
                        bar_dist = p2["index"] - p1["index"]
                        if bar_dist < 4 or p1["price"] <= p2["price"]:
                            continue
                        slope = (p2["price"] - p1["price"]) / bar_dist
                        diff = p1["price"] - p2["price"]
                        if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr:
                            continue

                        # Penetration check between anchors
                        penetrated = False
                        for k in range(p1["index"] + 1, p2["index"]):
                            lp = p1["price"] + slope * (k - p1["index"])
                            if candles_to_t[k]["close"] > lp + 0.25 * atr:
                                penetrated = True
                                break
                        if penetrated:
                            continue

                        # Check line interaction on current bar
                        latest_lp = p1["price"] + slope * (t_idx - p1["index"])
                        dist_close = latest_lp - curr_c["close"]
                        is_near = abs(dist_close) <= 1.0 * atr
                        if not is_near:
                            continue

                        # Context & Flags
                        htf_ctx = "AGAINST_HTF" if htf_trend == "BULLISH" else ("ALIGNED" if htf_trend == "BEARISH" else "NEUTRAL")

                        sub5 = candles_to_t[max(0, t_idx - 5):]
                        sub20 = candles_to_t[max(0, t_idx - 20):]
                        a5 = calculate_atr(sub5, 5)
                        a20 = calculate_atr(sub20, 20)
                        comp_ratio = (a5 / a20) if a20 > 0 else 1.0
                        is_comp = comp_ratio < DEFAULT_COMPRESSION_THRESHOLD

                        flags = compute_structural_risk_flags(
                            htf_context=htf_ctx,
                            interaction_state="COMPRESSION" if is_comp else "TESTING",
                            compression_ratio=comp_ratio,
                            compression_threshold=DEFAULT_COMPRESSION_THRESHOLD,
                            status="ACTIVE",
                        )

                        # Future outcome check over HORIZON
                        broken_out = False
                        for f_idx in range(t_idx + 1, min(n_ltf, t_idx + 1 + HORIZON)):
                            fut_lp = p1["price"] + slope * (f_idx - p1["index"])
                            fut_atr = calculate_atr(c_ltf[max(0, f_idx-14):f_idx+1], 14)
                            if c_ltf[f_idx]["close"] > fut_lp + 0.25 * fut_atr:
                                broken_out = True
                                break

                        # Record stats
                        st = dataset_stats[stats_key]
                        st["total_lines"] += 1
                        grand_total_lines += 1
                        if htf_ctx == "ALIGNED":
                            st["aligned"] += 1
                            if broken_out: st["aligned_breakouts"] += 1
                        elif htf_ctx == "AGAINST_HTF":
                            st["against_htf"] += 1
                            if broken_out: st["against_htf_breakouts"] += 1
                        elif htf_ctx == "NEUTRAL":
                            st["neutral"] += 1

                        if is_comp:
                            st["compression"] += 1
                            if broken_out: st["compression_breakouts"] += 1

                # 2. Evaluate support lines
                for i in range(len(lows) - 1):
                    for j in range(i + 1, len(lows)):
                        p1, p2 = lows[i], lows[j]
                        bar_dist = p2["index"] - p1["index"]
                        if bar_dist < 4 or p2["price"] <= p1["price"]:
                            continue
                        slope = (p2["price"] - p1["price"]) / bar_dist
                        diff = p2["price"] - p1["price"]
                        if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr:
                            continue

                        penetrated = False
                        for k in range(p1["index"] + 1, p2["index"]):
                            lp = p1["price"] + slope * (k - p1["index"])
                            if candles_to_t[k]["close"] < lp - 0.25 * atr:
                                penetrated = True
                                break
                        if penetrated:
                            continue

                        latest_lp = p1["price"] + slope * (t_idx - p1["index"])
                        dist_close = curr_c["close"] - latest_lp
                        is_near = abs(dist_close) <= 1.0 * atr
                        if not is_near:
                            continue

                        htf_ctx = "ALIGNED" if htf_trend == "BULLISH" else ("AGAINST_HTF" if htf_trend == "BEARISH" else "NEUTRAL")

                        sub5 = candles_to_t[max(0, t_idx - 5):]
                        sub20 = candles_to_t[max(0, t_idx - 20):]
                        a5 = calculate_atr(sub5, 5)
                        a20 = calculate_atr(sub20, 20)
                        comp_ratio = (a5 / a20) if a20 > 0 else 1.0
                        is_comp = comp_ratio < DEFAULT_COMPRESSION_THRESHOLD

                        flags = compute_structural_risk_flags(
                            htf_context=htf_ctx,
                            interaction_state="COMPRESSION" if is_comp else "TESTING",
                            compression_ratio=comp_ratio,
                            compression_threshold=DEFAULT_COMPRESSION_THRESHOLD,
                            status="ACTIVE",
                        )

                        broken_out = False
                        for f_idx in range(t_idx + 1, min(n_ltf, t_idx + 1 + HORIZON)):
                            fut_lp = p1["price"] + slope * (f_idx - p1["index"])
                            fut_atr = calculate_atr(c_ltf[max(0, f_idx-14):f_idx+1], 14)
                            if c_ltf[f_idx]["close"] < fut_lp - 0.25 * fut_atr:
                                broken_out = True
                                break

                        st = dataset_stats[stats_key]
                        st["total_lines"] += 1
                        grand_total_lines += 1
                        if htf_ctx == "ALIGNED":
                            st["aligned"] += 1
                            if broken_out: st["aligned_breakouts"] += 1
                        elif htf_ctx == "AGAINST_HTF":
                            st["against_htf"] += 1
                            if broken_out: st["against_htf_breakouts"] += 1
                        elif htf_ctx == "NEUTRAL":
                            st["neutral"] += 1

                        if is_comp:
                            st["compression"] += 1
                            if broken_out: st["compression_breakouts"] += 1

    print("\n" + "=" * 100)
    print("STATISTICAL RESULTS PER SYMBOL AND TIMEFRAME:")
    print("=" * 100)
    print(f"{'Symbol/TF':<12} | {'Lines':<6} | {'ALIGNED (Rate)':<18} | {'AGAINST_HTF (Rate)':<20} | {'COMPRESSION':<14} | {'AGAINST Breakout':<18}")
    print("-" * 100)

    total_aligned = 0
    total_against = 0
    total_neutral = 0
    total_comp = 0
    total_against_bo = 0
    total_aligned_bo = 0
    total_comp_bo = 0

    for key, st in sorted(dataset_stats.items()):
        n = st["total_lines"]
        if n == 0: continue
        total_aligned += st["aligned"]
        total_against += st["against_htf"]
        total_neutral += st["neutral"]
        total_comp += st["compression"]
        total_against_bo += st["against_htf_breakouts"]
        total_aligned_bo += st["aligned_breakouts"]
        total_comp_bo += st["compression_breakouts"]

        p_al, al_l, al_h = wilson_score_ci(st["aligned"], n)
        p_ag, ag_l, ag_h = wilson_score_ci(st["against_htf"], n)
        p_cp, cp_l, cp_h = wilson_score_ci(st["compression"], n)
        p_ag_bo, ag_bo_l, ag_bo_h = wilson_score_ci(st["against_htf_breakouts"], st["against_htf"]) if st["against_htf"] > 0 else (0, 0, 0)

        print(f"{key:<12} | {n:<6} | {st['aligned']:>3} ({p_al*100:4.1f}% [{al_l*100:4.1f}-{al_h*100:4.1f}%]) | {st['against_htf']:>3} ({p_ag*100:4.1f}% [{ag_l*100:4.1f}-{ag_h*100:4.1f}%]) | {st['compression']:>3} ({p_cp*100:4.1f}%) | {st['against_htf_breakouts']:>3}/{st['against_htf']:<3} ({p_ag_bo*100:4.1f}%)")

    print("=" * 100)
    print(f"\nAGGREGATE STATISTICAL AUDIT SUMMARY (Total Evaluated Lines: {grand_total_lines}):")
    print("-" * 100)

    # 95% CIs for frequencies
    p_al, al_l, al_h = wilson_score_ci(total_aligned, grand_total_lines)
    p_ag, ag_l, ag_h = wilson_score_ci(total_against, grand_total_lines)
    p_ne, ne_l, ne_h = wilson_score_ci(total_neutral, grand_total_lines)
    p_cp, cp_l, cp_h = wilson_score_ci(total_comp, grand_total_lines)

    # Breakout rates with 95% CIs
    p_ag_bo, ag_bo_l, ag_bo_h = wilson_score_ci(total_against_bo, total_against)
    p_al_bo, al_bo_l, al_bo_h = wilson_score_ci(total_aligned_bo, total_aligned)
    p_cp_bo, cp_bo_l, cp_bo_h = wilson_score_ci(total_comp_bo, total_comp)

    print(f"1. HTF Context Frequency:")
    print(f"   - ALIGNED:     {total_aligned:>4} / {grand_total_lines} = {p_al*100:5.1f}% [95% CI: {al_l*100:5.1f}% - {al_h*100:5.1f}%]")
    print(f"   - AGAINST_HTF: {total_against:>4} / {grand_total_lines} = {p_ag*100:5.1f}% [95% CI: {ag_l*100:5.1f}% - {ag_h*100:5.1f}%]")
    print(f"   - NEUTRAL:     {total_neutral:>4} / {grand_total_lines} = {p_ne*100:5.1f}% [95% CI: {ne_l*100:5.1f}% - {ne_h*100:5.1f}%]")

    print(f"\n2. Risk Flag Frequency:")
    print(f"   - COMPRESSION: {total_comp:>4} / {grand_total_lines} = {p_cp*100:5.1f}% [95% CI: {cp_l*100:5.1f}% - {cp_h*100:5.1f}%]")

    print(f"\n3. Structural Risk Validation (Breakout / Failure Rates over H={HORIZON} bars):")
    print(f"   - AGAINST_HTF Breakout Rate: {total_against_bo:>4} / {total_against} = {p_ag_bo*100:5.1f}% [95% CI: {ag_bo_l*100:5.1f}% - {ag_bo_h*100:5.1f}%]")
    print(f"   - ALIGNED Breakout Rate:     {total_aligned_bo:>4} / {total_aligned} = {p_al_bo*100:5.1f}% [95% CI: {al_bo_l*100:5.1f}% - {al_bo_h*100:5.1f}%]")
    print(f"   - COMPRESSION Breakout Rate: {total_comp_bo:>4} / {total_comp} = {p_cp_bo*100:5.1f}% [95% CI: {cp_bo_l*100:5.1f}% - {cp_bo_h*100:5.1f}%]")

    # Difference in breakout rate between AGAINST_HTF and ALIGNED
    risk_multiplier = (p_ag_bo / max(p_al_bo, 1e-6)) if p_al_bo > 0 else 0.0
    print(f"\n4. Risk Ratio (AGAINST_HTF vs ALIGNED): {risk_multiplier:.2f}x higher breakout risk when going against HTF structure.")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(run_statistical_audit())
