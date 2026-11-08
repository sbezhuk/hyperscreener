import asyncio
import sys
import os
import json
import math
import random
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Optional

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.analyzer.trendline import (
    detect_timeframe_trendlines,
    calculate_atr,
    evaluate_htf_structural_context,
    _resolve_timeframe_step_seconds,
    DEFAULT_COMPRESSION_THRESHOLD,
)
from app.analyzer.screener import enrich_signals_with_trendline_context
from app.analyzer.liquidity import detect_liquidity_and_sweeps
from app.analyzer.fvg import detect_fvgs
from app.analyzer.levels import analyze_levels
from app.analyzer.structure import analyze_market_structure
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
    resolve_research_timeframes,
    get_htf_for_timeframe,
)

BASE_TF = "15m"
HTF_TF = "1h"
HORIZON_BARS = 20
TP_ATR_MULT = 2.0
SL_ATR_MULT = 1.0
FEE_PCT = 0.0005        # 0.05% taker fee
SLIPPAGE_PCT = 0.0002    # 0.02% slippage

RESULTS_OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "phase6_simulation_results.json")


def wilson_score_ci(successes: int, total: int, z: float = 1.96) -> Tuple[float, float, float]:
    """Calculates Wilson score 95% confidence interval for a proportion."""
    if total == 0:
        return 0.0, 0.0, 0.0
    p_hat = successes / total
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) + (z**2) / (4.0 * total)) / total)) / denom
    return p_hat, max(0.0, center - margin), min(1.0, center + margin)


def clustered_bootstrap_expectancy(trades: List[Dict[str, Any]], num_bootstraps: int = 1000, seed: int = 42) -> Tuple[float, float, float]:
    """
    Clustered bootstrap for mean trade expectancy (in ATR).
    Clusters by (coin, day) to respect intra-day and cross-asset correlations.
    """
    if not trades:
        return 0.0, 0.0, 0.0

    clusters = defaultdict(list)
    for tr in trades:
        # Cluster key: (coin, calendar_day)
        day_key = (tr["coin"], tr["entry_time"] // 86400)
        clusters[day_key].append(tr)

    keys = list(clusters.keys())
    if not keys:
        return 0.0, 0.0, 0.0

    rng = random.Random(seed)
    bootstrap_means = []
    for _ in range(num_bootstraps):
        sampled = []
        for _ in range(len(keys)):
            k = rng.choice(keys)
            sampled.extend(clusters[k])
        if sampled:
            m = sum(t["pnl_atr"] for t in sampled) / len(sampled)
            bootstrap_means.append(m)

    bootstrap_means.sort()
    mean_val = sum(t["pnl_atr"] for t in trades) / len(trades)
    ci_low = bootstrap_means[int(0.025 * len(bootstrap_means))] if bootstrap_means else mean_val
    ci_high = bootstrap_means[int(0.975 * len(bootstrap_means))] if bootstrap_means else mean_val
    return mean_val, ci_low, ci_high


def calculate_two_sample_p_value(group_a: List[float], group_b: List[float]) -> float:
    """Calculates Welch's t-test p-value between two independent samples."""
    na, nb = len(group_a), len(group_b)
    if na < 5 or nb < 5:
        return 1.0
    ma = sum(group_a) / na
    mb = sum(group_b) / nb
    va = sum((x - ma)**2 for x in group_a) / (na - 1)
    vb = sum((x - mb)**2 for x in group_b) / (nb - 1)
    denom = math.sqrt(va / na + vb / nb)
    if denom <= 1e-9:
        return 1.0
    t_stat = abs(ma - mb) / denom
    # Normal approximation for p-value
    p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(t_stat / math.sqrt(2))))
    return max(0.0, min(1.0, p_val))


def benjamini_hochberg_correction(p_values: List[float], fdr: float = 0.05) -> List[Tuple[float, bool]]:
    """Applies Benjamini-Hochberg FDR correction for multiple hypotheses."""
    m = len(p_values)
    if m == 0:
        return []
    sorted_pairs = sorted(enumerate(p_values), key=lambda x: x[1])
    is_significant = [False] * m
    max_k = -1

    for rank, (orig_idx, p) in enumerate(sorted_pairs, start=1):
        crit_val = (rank / m) * fdr
        if p <= crit_val:
            max_k = rank

    if max_k != -1:
        for rank in range(1, max_k + 1):
            orig_idx = sorted_pairs[rank - 1][0]
            is_significant[orig_idx] = True

    return [(p, is_significant[i]) for i, p in enumerate(p_values)]


def simulate_trade(
    candles: List[Dict[str, Any]],
    entry_idx: int,
    entry_price: float,
    direction: str,
    atr: float,
    tp_mult: float = TP_ATR_MULT,
    sl_mult: float = SL_ATR_MULT,
    horizon: int = HORIZON_BARS,
) -> Dict[str, Any]:
    """
    Simulates a trade forward for LONG or SHORT with transaction friction,
    conservative simultaneous touch ordering, MFE, MAE, and net PnL accounting.
    """
    n = len(candles)
    is_long = direction.upper() == "LONG"

    # Execution price with entry slippage
    real_entry = entry_price * (1.0 + SLIPPAGE_PCT) if is_long else entry_price * (1.0 - SLIPPAGE_PCT)

    tp_price = real_entry + (tp_mult * atr) if is_long else real_entry - (tp_mult * atr)
    sl_price = real_entry - (sl_mult * atr) if is_long else real_entry + (sl_mult * atr)

    mfe_atr = 0.0
    mae_atr = 0.0
    outcome = "TIMEOUT"
    exit_idx = min(n - 1, entry_idx + horizon)
    exit_price = candles[exit_idx]["close"]

    for k in range(entry_idx + 1, min(n, entry_idx + horizon + 1)):
        c = candles[k]
        if is_long:
            high_diff = c["high"] - real_entry
            low_diff = real_entry - c["low"]
            cur_mfe = max(0.0, high_diff / max(atr, 1e-6))
            cur_mae = max(0.0, low_diff / max(atr, 1e-6))
            if cur_mfe > mfe_atr: mfe_atr = cur_mfe
            if cur_mae > mae_atr: mae_atr = cur_mae

            # Conservative: SL hit checked first
            if c["low"] <= sl_price:
                outcome = "SL"
                exit_price = sl_price * (1.0 - SLIPPAGE_PCT)
                exit_idx = k
                break
            if c["high"] >= tp_price:
                outcome = "TP"
                exit_price = tp_price * (1.0 - SLIPPAGE_PCT)
                exit_idx = k
                break
        else: # SHORT
            low_diff = real_entry - c["low"]
            high_diff = c["high"] - real_entry
            cur_mfe = max(0.0, low_diff / max(atr, 1e-6))
            cur_mae = max(0.0, high_diff / max(atr, 1e-6))
            if cur_mfe > mfe_atr: mfe_atr = cur_mfe
            if cur_mae > mae_atr: mae_atr = cur_mae

            # Conservative: SL hit checked first
            if c["high"] >= sl_price:
                outcome = "SL"
                exit_price = sl_price * (1.0 + SLIPPAGE_PCT)
                exit_idx = k
                break
            if c["low"] <= tp_price:
                outcome = "TP"
                exit_price = tp_price * (1.0 + SLIPPAGE_PCT)
                exit_idx = k
                break

    # PnL accounting net of round-trip fees (0.05% + 0.05% = 0.10%)
    gross_ret = (exit_price - real_entry) / real_entry if is_long else (real_entry - exit_price) / real_entry
    net_ret = gross_ret - (2.0 * FEE_PCT)
    pnl_atr = ((exit_price - real_entry) if is_long else (real_entry - exit_price)) / max(atr, 1e-6) - ((real_entry * 2.0 * FEE_PCT) / max(atr, 1e-6))
    win = 1 if outcome == "TP" or (outcome == "TIMEOUT" and net_ret > 0) else 0

    return {
        "outcome": outcome,
        "win": win,
        "entry_price": real_entry,
        "exit_price": exit_price,
        "net_return_pct": net_ret,
        "pnl_atr": pnl_atr,
        "mfe_atr": mfe_atr,
        "mae_atr": mae_atr,
        "bars_held": exit_idx - entry_idx,
    }


def compute_aggregate_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculates comprehensive trading performance and risk metrics."""
    n = len(trades)
    if n == 0:
        return {
            "n": 0, "win_rate": 0.0, "win_ci": (0.0, 0.0), "profit_factor": 0.0,
            "expectancy_atr": 0.0, "expectancy_ci": (0.0, 0.0),
            "mfe_atr": 0.0, "mae_atr": 0.0, "avg_rr": 0.0, "max_drawdown_atr": 0.0,
            "loss_rate": 0.0,
        }

    wins = [t for t in trades if t["win"] == 1]
    losses = [t for t in trades if t["win"] == 0]
    win_cnt = len(wins)
    p_hat, ci_l, ci_u = wilson_score_ci(win_cnt, n)

    gross_gains = sum(t["pnl_atr"] for t in wins if t["pnl_atr"] > 0)
    gross_losses = abs(sum(t["pnl_atr"] for t in losses if t["pnl_atr"] < 0))
    profit_factor = gross_gains / gross_losses if gross_losses > 1e-6 else (99.0 if gross_gains > 0 else 1.0)

    mean_exp, exp_ci_l, exp_ci_u = clustered_bootstrap_expectancy(trades)

    avg_mfe = sum(t["mfe_atr"] for t in trades) / n
    avg_mae = sum(t["mae_atr"] for t in trades) / n

    # Drawdown calculation over chronological sequence
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum += t["pnl_atr"]
        if cum > peak: peak = cum
        dd = peak - cum
        if dd > max_dd: max_dd = dd

    avg_win_atr = sum(t["pnl_atr"] for t in wins) / max(len(wins), 1)
    avg_loss_atr = abs(sum(t["pnl_atr"] for t in losses) / max(len(losses), 1))
    avg_rr = avg_win_atr / max(avg_loss_atr, 1e-4)

    return {
        "n": n,
        "win_rate": p_hat * 100.0,
        "win_ci": (ci_l * 100.0, ci_u * 100.0),
        "profit_factor": profit_factor,
        "expectancy_atr": mean_exp,
        "expectancy_ci": (exp_ci_l, exp_ci_u),
        "mfe_atr": avg_mfe,
        "mae_atr": avg_mae,
        "avg_rr": avg_rr,
        "max_drawdown_atr": max_dd,
        "loss_rate": (len(losses) / n) * 100.0,
    }


async def run_simulation():
    print("=" * 100)
    print("PHASE 6: TRADING INTELLIGENCE VALIDATION & EMPIRICAL BACKTEST ENGINE")
    print("=" * 100)

    # Universal dynamic discovery of liquid perpetual assets
    discovered_coins = await resolve_research_coins(min_volume_usd=5_000_000.0, top_n=10)
    print(f"Universally discovered {len(discovered_coins)} liquid assets for Phase 6: {discovered_coins}")

    ltf_step = _resolve_timeframe_step_seconds(interval_str=BASE_TF, default_step=900)
    htf_step = _resolve_timeframe_step_seconds(interval_str=HTF_TF, default_step=3600)

    all_simulated_trades: List[Dict[str, Any]] = []

    for coin in discovered_coins:
        ds_15m = await get_single_dataset(coin, BASE_TF)
        ds_1h = await get_single_dataset(coin, HTF_TF)
        c_15m = ds_15m["candles"]
        c_1h = ds_1h["candles"]
        n_15 = len(c_15m)

        if n_15 < 100 or len(c_1h) < 40:
            print(f"Skipping {coin}: insufficient data")
            continue

        n_in = int(n_15 * 0.60)
        n_val = int(n_15 * 0.20)

        print(f"\nProcessing {coin}: {n_15} 15m bars (In-sample: 0..{n_in}, Val: {n_in}..{n_in+n_val}, OOS: {n_in+n_val}..{n_15})...")

        # Step bar-by-bar walk-forward
        for t_idx in range(50, n_15 - HORIZON_BARS):
            curr_c = c_15m[t_idx]
            curr_time = curr_c["time"]
            candles_sub = c_15m[:t_idx + 1]
            atr = calculate_atr(candles_sub, 14)
            if atr <= 0: continue

            # Determine dataset split
            if t_idx < n_in:
                split = "IN_SAMPLE"
            elif t_idx < n_in + n_val:
                split = "VALIDATION"
            else:
                split = "OUT_OF_SAMPLE"

            # Strict Point-in-Time 1h candles: closed at or before current bar close
            eval_time = curr_time + ltf_step
            pit_htf = [c for c in c_1h if int(c.get("close_time") or (c["time"] + htf_step)) <= eval_time]
            if len(pit_htf) < 20: continue

            # 1. Detect local levels and sweeps
            levels_res = analyze_levels(candles_sub, interval=BASE_TF)
            all_levels = levels_res.get("resistances", []) + levels_res.get("supports", [])

            liq_data = detect_liquidity_and_sweeps(
                candles_sub,
                interval=BASE_TF,
                levels=all_levels,
                oi_tracker=None,
                coin=coin,
                only_confirmed=False,
            )

            # 2. Detect local trendlines
            tls = detect_timeframe_trendlines(candles_sub, interval=BASE_TF)

            # 3. Detect local FVGs
            fvgs = detect_fvgs(candles_sub, interval=BASE_TF)

            # Compile signals on bar t_idx
            raw_signals = []

            # Sweeps (False Breakout)
            for sw in liq_data.get("sweeps", []):
                # Only signals created/confirmed on or immediately prior to the current bar
                if abs(sw.get("time", 0) - curr_time) <= ltf_step * 2:
                    raw_signals.append({
                        "id": sw.get("id") or f"sw-{sw['time']}",
                        "coin": coin,
                        "interval": BASE_TF,
                        "category": "sweep",
                        "title": sw.get("formation", "Sweep"),
                        "direction": sw.get("direction", "LONG"),
                        "price": sw.get("levelPrice", curr_c["close"]),
                        "time": curr_time,
                        "entry_time": curr_time,
                        "confirmationStatus": sw.get("confirmationStatus", "UNCONFIRMED"),
                    })

            # FVGs
            for fvg in fvgs:
                if abs(fvg.get("created_at", 0) - curr_time) <= ltf_step:
                    raw_signals.append({
                        "id": fvg.get("id") or f"fvg-{fvg.get('created_at', curr_time)}",
                        "coin": coin,
                        "interval": BASE_TF,
                        "category": "fvg",
                        "title": f"FVG {fvg.get('type')}",
                        "direction": "LONG" if fvg.get("type") == "bullish" else "SHORT",
                        "price": curr_c["close"],
                        "time": curr_time,
                        "entry_time": curr_time,
                    })

            # Trendlines
            for tl in tls:
                state = tl.get("interaction_state", "ACTIVE")
                if state in ["BREAKOUT", "RETEST", "TESTING"]:
                    raw_signals.append({
                        "id": tl.get("id") or f"tl-{tl.get('timeframe')}",
                        "coin": coin,
                        "interval": BASE_TF,
                        "category": "trendline",
                        "title": tl.get("label", "Trendline"),
                        "direction": "LONG" if tl.get("line_type") == "support_trendline" else "SHORT",
                        "price": curr_c["close"],
                        "time": curr_time,
                        "entry_time": curr_time,
                        "structural_quality": tl.get("structural_quality", tl.get("strength", 50.0)),
                        "interaction_state": state,
                    })

            if not raw_signals:
                continue

            # Enrich signals with Trendline Structural Intelligence
            enriched = enrich_signals_with_trendline_context(
                signals=raw_signals,
                active_trendlines=tls,
                candles=candles_sub,
                interval=BASE_TF,
                coin=coin,
                htf_candles=pit_htf,
                atr_period=14,
                compression_threshold=DEFAULT_COMPRESSION_THRESHOLD,
            )

            # Simulate execution for each signal
            for sig in enriched:
                ctx = sig.get("structuralContext") or {}
                direction = sig.get("direction", "LONG")
                trade_res = simulate_trade(
                    candles=c_15m,
                    entry_idx=t_idx,
                    entry_price=curr_c["close"],
                    direction=direction,
                    atr=atr,
                    tp_mult=TP_ATR_MULT,
                    sl_mult=SL_ATR_MULT,
                    horizon=HORIZON_BARS,
                )

                trade_record = {
                    "coin": coin,
                    "bar_idx": t_idx,
                    "entry_time": curr_time,
                    "split": split,
                    "direction": direction,
                    "category": sig.get("category"),
                    "title": sig.get("title"),
                    "atr": atr,
                    # Structural context fields
                    "structural_tier": ctx.get("structuralTier", "TIER_2_STANDARD"),
                    "htf_alignment": ctx.get("htfAlignment", "UNAVAILABLE"),
                    "has_support_confluence": ctx.get("hasSupportConfluence", False),
                    "dist_support_atr": ctx.get("distanceToSupportAtr"),
                    "dist_resistance_atr": ctx.get("distanceToResistanceAtr"),
                    "confluent_line_q": ctx.get("confluentLineQ"),
                    "nearest_support_q": ctx.get("nearestSupportQ"),
                    "nearest_res_q": ctx.get("nearestResistanceQ"),
                    "is_compression": ctx.get("isCompression", False),
                    "compression_ratio": ctx.get("compressionRatio"),
                    "is_retest": ctx.get("isRetest", False),
                    "risk_flags": ctx.get("riskFlags", []),
                    # Trade outcome
                    **trade_res,
                }
                all_simulated_trades.append(trade_record)

    print(f"\nTotal Simulated Trades Generated: {len(all_simulated_trades)}")

    # Save raw trades to scratch
    with open(RESULTS_OUTPUT_FILE, "w") as f:
        json.dump(all_simulated_trades, f, indent=2)
    print(f"Saved simulation trades to {RESULTS_OUTPUT_FILE}")

    # =========================================================================
    # MODULE B: BASELINE VS STRUCTURAL INTELLIGENCE
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE B: BASELINE VS STRUCTURAL INTELLIGENCE TIERS")
    print("=" * 90)

    base_metrics = compute_aggregate_metrics(all_simulated_trades)
    tier1_trades = [t for t in all_simulated_trades if t["structural_tier"] == "TIER_1_CONFLUENT"]
    tier2_trades = [t for t in all_simulated_trades if t["structural_tier"] == "TIER_2_STANDARD"]
    tier3_trades = [t for t in all_simulated_trades if t["structural_tier"] == "TIER_3_WARNING"]

    tier1_metrics = compute_aggregate_metrics(tier1_trades)
    tier2_metrics = compute_aggregate_metrics(tier2_trades)
    tier3_metrics = compute_aggregate_metrics(tier3_trades)

    def print_tier_row(name: str, m: Dict[str, Any]):
        ci_w = f"[{m['win_ci'][0]:.1f}%..{m['win_ci'][1]:.1f}%]"
        ci_e = f"[{m['expectancy_ci'][0]:+.2f}..{m['expectancy_ci'][1]:+.2f}]"
        print(f"{name:<20} | N={m['n']:>4} | WR: {m['win_rate']:>5.1f}% {ci_w:<16} | PF: {m['profit_factor']:>4.2f} | Exp: {m['expectancy_atr']:>+5.2f}R {ci_e:<16} | MFE: {m['mfe_atr']:>4.2f}R | MAE: {m['mae_atr']:>4.2f}R | MaxDD: {m['max_drawdown_atr']:>4.1f}R")

    print_tier_row("Baseline (All)", base_metrics)
    print_tier_row("TIER_1_CONFLUENT", tier1_metrics)
    print_tier_row("TIER_2_STANDARD", tier2_metrics)
    print_tier_row("TIER_3_WARNING", tier3_metrics)

    # Statistical significance of Tier 1 vs Baseline and Tier 3 vs Baseline
    p_t1 = calculate_two_sample_p_value([t["pnl_atr"] for t in tier1_trades], [t["pnl_atr"] for t in all_simulated_trades])
    p_t3 = calculate_two_sample_p_value([t["pnl_atr"] for t in tier3_trades], [t["pnl_atr"] for t in all_simulated_trades])
    print(f"\nSignificance tests vs Baseline: Tier 1 p-val={p_t1:.4f} | Tier 3 (Warning) p-val={p_t3:.4f}")

    # =========================================================================
    # MODULE C: INDEPENDENT FEATURE ANALYSIS
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE C1: HTF ALIGNMENT INDEPENDENT ANALYSIS")
    print("=" * 90)
    for htf_val in ["ALIGNED", "NEUTRAL", "AGAINST_HTF", "UNAVAILABLE"]:
        sub = [t for t in all_simulated_trades if t["htf_alignment"] == htf_val]
        m = compute_aggregate_metrics(sub)
        print_tier_row(f"HTF: {htf_val}", m)

    print("\n" + "=" * 90)
    print("MODULE C2: SUPPORT CONFLUENCE & DISTANCE TO SUPPORT (LONG ONLY)")
    print("=" * 90)
    long_trades = [t for t in all_simulated_trades if t["direction"] == "LONG"]
    dist_brackets = [
        ("< 0.50 ATR", lambda t: t["dist_support_atr"] is not None and t["dist_support_atr"] < 0.50),
        ("0.50 - 1.00 ATR", lambda t: t["dist_support_atr"] is not None and 0.50 <= t["dist_support_atr"] < 1.00),
        ("1.00 - 1.50 ATR", lambda t: t["dist_support_atr"] is not None and 1.00 <= t["dist_support_atr"] < 1.50),
        ("1.50 - 2.50 ATR", lambda t: t["dist_support_atr"] is not None and 1.50 <= t["dist_support_atr"] < 2.50),
        ("> 2.50 ATR / None", lambda t: t["dist_support_atr"] is None or t["dist_support_atr"] >= 2.50),
    ]
    for b_name, b_fn in dist_brackets:
        sub = [t for t in long_trades if b_fn(t)]
        m = compute_aggregate_metrics(sub)
        print_tier_row(f"SupDist {b_name}", m)

    print("\n" + "=" * 90)
    print("MODULE C3: VOLATILITY COMPRESSION RATIO ANALYSIS")
    print("=" * 90)
    comp_brackets = [
        ("< 0.55 (Severe)", lambda t: t["compression_ratio"] is not None and t["compression_ratio"] < 0.55),
        ("0.55 - 0.65 (High)", lambda t: t["compression_ratio"] is not None and 0.55 <= t["compression_ratio"] < 0.65),
        ("0.65 - 0.75 (Moderate)", lambda t: t["compression_ratio"] is not None and 0.65 <= t["compression_ratio"] < 0.75),
        ("0.75 - 0.85 (Mild)", lambda t: t["compression_ratio"] is not None and 0.75 <= t["compression_ratio"] < 0.85),
        ("> 0.85 (Normal/None)", lambda t: t["compression_ratio"] is None or t["compression_ratio"] >= 0.85),
    ]
    for b_name, b_fn in comp_brackets:
        sub = [t for t in all_simulated_trades if b_fn(t)]
        m = compute_aggregate_metrics(sub)
        print_tier_row(f"Comp {b_name}", m)

    print("\n" + "=" * 90)
    print("MODULE C4: BREAKOUT / RETEST ANALYSIS")
    print("=" * 90)
    retest_trades = [t for t in all_simulated_trades if t["is_retest"]]
    breakout_trades = [t for t in all_simulated_trades if "BREAKOUT" in t["risk_flags"]]
    normal_trades = [t for t in all_simulated_trades if not t["is_retest"] and "BREAKOUT" not in t["risk_flags"]]
    print_tier_row("Retest Confirmed", compute_aggregate_metrics(retest_trades))
    print_tier_row("Breakout Active", compute_aggregate_metrics(breakout_trades))
    print_tier_row("No Retest/Breakout", compute_aggregate_metrics(normal_trades))

    print("\n" + "=" * 90)
    print("MODULE C5: STRUCTURAL QUALITY (Q) STRATIFICATION")
    print("=" * 90)
    q_brackets = [
        ("Q < 60", lambda t: (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) < 60),
        ("Q 60 - 70", lambda t: 60 <= (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) < 70),
        ("Q 70 - 80", lambda t: 70 <= (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) < 80),
        ("Q 80 - 90", lambda t: 80 <= (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) < 90),
        ("Q >= 90", lambda t: (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) >= 90),
    ]
    for b_name, b_fn in q_brackets:
        sub = [t for t in all_simulated_trades if b_fn(t)]
        m = compute_aggregate_metrics(sub)
        print_tier_row(f"Quality {b_name}", m)

    # =========================================================================
    # MODULE D: LONG / SHORT ASYMMETRY ANALYSIS
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE D: LONG VS SHORT ASYMMETRY")
    print("=" * 90)
    short_trades = [t for t in all_simulated_trades if t["direction"] == "SHORT"]

    print("--- LONG TRADES BREAKDOWN ---")
    print_tier_row("LONG Baseline", compute_aggregate_metrics(long_trades))
    print_tier_row("LONG ALIGNED", compute_aggregate_metrics([t for t in long_trades if t["htf_alignment"] == "ALIGNED"]))
    print_tier_row("LONG AGAINST_HTF", compute_aggregate_metrics([t for t in long_trades if t["htf_alignment"] == "AGAINST_HTF"]))
    print_tier_row("LONG Severe Comp (<0.55)", compute_aggregate_metrics([t for t in long_trades if t["compression_ratio"] is not None and t["compression_ratio"] < 0.55]))
    print_tier_row("LONG Tier 1 Confluent", compute_aggregate_metrics([t for t in long_trades if t["structural_tier"] == "TIER_1_CONFLUENT"]))
    print_tier_row("LONG Tier 3 Warning", compute_aggregate_metrics([t for t in long_trades if t["structural_tier"] == "TIER_3_WARNING"]))

    print("\n--- SHORT TRADES BREAKDOWN ---")
    print_tier_row("SHORT Baseline", compute_aggregate_metrics(short_trades))
    print_tier_row("SHORT ALIGNED", compute_aggregate_metrics([t for t in short_trades if t["htf_alignment"] == "ALIGNED"]))
    print_tier_row("SHORT AGAINST_HTF", compute_aggregate_metrics([t for t in short_trades if t["htf_alignment"] == "AGAINST_HTF"]))
    print_tier_row("SHORT Severe Comp (<0.55)", compute_aggregate_metrics([t for t in short_trades if t["compression_ratio"] is not None and t["compression_ratio"] < 0.55]))
    print_tier_row("SHORT Tier 3 Warning", compute_aggregate_metrics([t for t in short_trades if t["structural_tier"] == "TIER_3_WARNING"]))

    # =========================================================================
    # MODULE E: STATISTICAL VALIDATION & MULTIPLE HYPOTHESES CORRECTION
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE E: STATISTICAL VALIDATION & BENJAMINI-HOCHBERG FDR CORRECTION")
    print("=" * 90)
    hypotheses = [
        ("H1: Tier 1 Confluence > Baseline", [t["pnl_atr"] for t in tier1_trades], [t["pnl_atr"] for t in all_simulated_trades]),
        ("H2: Tier 3 Warning < Baseline", [t["pnl_atr"] for t in tier3_trades], [t["pnl_atr"] for t in all_simulated_trades]),
        ("H3: HTF ALIGNED > HTF AGAINST", [t["pnl_atr"] for t in all_simulated_trades if t["htf_alignment"] == "ALIGNED"], [t["pnl_atr"] for t in all_simulated_trades if t["htf_alignment"] == "AGAINST_HTF"]),
        ("H4: Severe Compression (<0.55) < Normal (>0.85)", [t["pnl_atr"] for t in all_simulated_trades if t["compression_ratio"] is not None and t["compression_ratio"] < 0.55], [t["pnl_atr"] for t in all_simulated_trades if t["compression_ratio"] is None or t["compression_ratio"] >= 0.85]),
        ("H5: Retest Confirmed > Baseline", [t["pnl_atr"] for t in retest_trades], [t["pnl_atr"] for t in all_simulated_trades]),
        ("H6: Support Dist < 0.50 ATR > Dist > 2.50 ATR (LONG)", [t["pnl_atr"] for t in long_trades if t["dist_support_atr"] is not None and t["dist_support_atr"] < 0.50], [t["pnl_atr"] for t in long_trades if t["dist_support_atr"] is None or t["dist_support_atr"] >= 2.50]),
        ("H7: High Quality Q>=80 > Low Quality Q<60", [t["pnl_atr"] for t in all_simulated_trades if (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) >= 80], [t["pnl_atr"] for t in all_simulated_trades if (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) < 60]),
    ]

    p_raw = [calculate_two_sample_p_value(h[1], h[2]) for h in hypotheses]
    bh_results = benjamini_hochberg_correction(p_raw, fdr=0.05)

    for i, (name, _, _) in enumerate(hypotheses):
        p_val, is_sig = bh_results[i]
        status = "SIGNIFICANT (FDR < 0.05)" if is_sig else "NOT SIGNIFICANT"
        print(f"  {name:<55} | p-value = {p_val:>7.5f} | {status}")

    # =========================================================================
    # MODULE F: FEATURE ABLATION STUDY
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE F: FEATURE ABLATION STUDY")
    print("=" * 90)
    ablation_configs = [
        ("1. Baseline (Raw)", lambda t: True),
        ("2. Baseline + Filter Against HTF", lambda t: t["htf_alignment"] != "AGAINST_HTF"),
        ("3. Baseline + Support Confluence (Dist < 1.0 ATR)", lambda t: t["dist_support_atr"] is not None and t["dist_support_atr"] < 1.0),
        ("4. Baseline + Filter Severe Compression (< 0.55)", lambda t: t["compression_ratio"] is None or t["compression_ratio"] >= 0.55),
        ("5. Baseline + Confirmed Retest", lambda t: t["is_retest"]),
        ("6. Baseline + Structural Quality (Q >= 70)", lambda t: (t.get("confluent_line_q") or t.get("nearest_support_q") or 50) >= 70),
        ("7. All Validated (No Against HTF & No Comp & Q>=70)", lambda t: t["htf_alignment"] != "AGAINST_HTF" and (t["compression_ratio"] is None or t["compression_ratio"] >= 0.55) and ((t.get("confluent_line_q") or t.get("nearest_support_q") or 50) >= 70)),
    ]
    for a_name, a_fn in ablation_configs:
        sub = [t for t in all_simulated_trades if a_fn(t)]
        m = compute_aggregate_metrics(sub)
        print_tier_row(a_name, m)

    # =========================================================================
    # MODULE G: ROBUSTNESS & GENERALIZATION (LEAVE-ONE-ASSET-OUT & WALK-FORWARD)
    # =========================================================================
    print("\n" + "=" * 90)
    print("MODULE G1: LEAVE-ONE-ASSET-OUT (LOAO) VALIDATION (TIER 1 & FILTERED)")
    print("=" * 90)
    for coin_out in discovered_coins:
        train_trades = [t for t in all_simulated_trades if t["coin"] != coin_out]
        test_trades = [t for t in all_simulated_trades if t["coin"] == coin_out]
        
        # Filtered trades on left-out coin
        test_filtered = [t for t in test_trades if t["htf_alignment"] != "AGAINST_HTF" and (t["compression_ratio"] is None or t["compression_ratio"] >= 0.55)]
        
        m_raw = compute_aggregate_metrics(test_trades)
        m_filt = compute_aggregate_metrics(test_filtered)
        print(f"Left out [{coin_out:<4}]: Raw WR={m_raw['win_rate']:>5.1f}% Exp={m_raw['expectancy_atr']:>+5.2f}R | Filtered WR={m_filt['win_rate']:>5.1f}% Exp={m_filt['expectancy_atr']:>+5.2f}R (Delta: {m_filt['expectancy_atr'] - m_raw['expectancy_atr']:>+4.2f}R)")

    print("\n" + "=" * 90)
    print("MODULE G2: CHRONOLOGICAL WALK-FORWARD OUT-OF-SAMPLE STABILITY")
    print("=" * 90)
    for sp_name in ["IN_SAMPLE", "VALIDATION", "OUT_OF_SAMPLE"]:
        sp_trades = [t for t in all_simulated_trades if t["split"] == sp_name]
        sp_filtered = [t for t in sp_trades if t["htf_alignment"] != "AGAINST_HTF" and (t["compression_ratio"] is None or t["compression_ratio"] >= 0.55)]
        m_raw = compute_aggregate_metrics(sp_trades)
        m_filt = compute_aggregate_metrics(sp_filtered)
        print(f"Split {sp_name:<13} | Raw WR={m_raw['win_rate']:>5.1f}% Exp={m_raw['expectancy_atr']:>+5.2f}R | Filtered WR={m_filt['win_rate']:>5.1f}% Exp={m_filt['expectancy_atr']:>+5.2f}R (Delta: {m_filt['expectancy_atr'] - m_raw['expectancy_atr']:>+4.2f}R)")

    print("\nPhase 6 Simulation & Validation Completed.")


if __name__ == "__main__":
    asyncio.run(run_simulation())
