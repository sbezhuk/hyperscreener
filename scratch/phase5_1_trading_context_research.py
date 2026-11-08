import asyncio
import sys
import os
import math
import random
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.hyperliquid import hl_client
from app.analyzer.trendline import (
    calculate_atr,
    find_swings_for_trendlines,
    evaluate_htf_structural_context,
    compute_structural_risk_flags,
    calculate_structural_quality,
    _resolve_timeframe_step_seconds,
    DEFAULT_COMPRESSION_THRESHOLD,
)
from app.analyzer.structure import analyze_market_structure
from app.analyzer.fvg import detect_and_track_fvgs
from app.analyzer.levels import find_pivot_points, cluster_levels
from research_pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_single_dataset,
    resolve_research_coins,
)

BASE_TF = "15m"
HTF_TF = "1h"
HORIZON_BARS = 20
TP_ATR_MULT = 2.0
SL_ATR_MULT = 1.0
FEE_PCT = 0.0005     # 0.05% taker fee
SLIPPAGE_PCT = 0.0002 # 0.02% slippage


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
    """Clustered bootstrap for mean trade expectancy (in ATR)."""
    if not trades:
        return 0.0, 0.0, 0.0
    # Cluster by coin
    clusters = defaultdict(list)
    for tr in trades:
        clusters[tr["coin"]].append(tr)
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


def simulate_forward_trade(
    candles: List[Dict[str, Any]],
    entry_idx: int,
    entry_price: float,
    atr: float,
    tp_mult: float = TP_ATR_MULT,
    sl_mult: float = SL_ATR_MULT,
    horizon: int = HORIZON_BARS,
) -> Dict[str, Any]:
    """
    Simulates a standard LONG trade forward with fixed ATR TP/SL and transaction friction.
    """
    n = len(candles)
    tp_price = entry_price + tp_mult * atr
    sl_price = entry_price - sl_mult * atr

    # Slippage on entry
    real_entry = entry_price * (1.0 + SLIPPAGE_PCT)

    mfe_atr = 0.0
    mae_atr = 0.0
    outcome = "TIMEOUT"
    exit_price = candles[min(n - 1, entry_idx + horizon)]["close"]
    exit_idx = min(n - 1, entry_idx + horizon)

    for k in range(entry_idx + 1, min(n, entry_idx + horizon + 1)):
        c = candles[k]
        high_diff = c["high"] - real_entry
        low_diff = real_entry - c["low"]

        cur_mfe = max(0.0, high_diff / max(atr, 1e-6))
        cur_mae = max(0.0, low_diff / max(atr, 1e-6))
        if cur_mfe > mfe_atr: mfe_atr = cur_mfe
        if cur_mae > mae_atr: mae_atr = cur_mae

        # Check SL first (conservative)
        if c["low"] <= sl_price:
            outcome = "SL"
            exit_price = sl_price * (1.0 - SLIPPAGE_PCT)
            exit_idx = k
            break
        # Check TP
        if c["high"] >= tp_price:
            outcome = "TP"
            exit_price = tp_price * (1.0 - SLIPPAGE_PCT)
            exit_idx = k
            break

    # PnL accounting net of fees
    gross_return_pct = (exit_price - real_entry) / real_entry
    # Two-way taker fees
    net_return_pct = gross_return_pct - (2.0 * FEE_PCT)
    pnl_atr = (exit_price - real_entry) / max(atr, 1e-6) - ((real_entry * 2.0 * FEE_PCT) / max(atr, 1e-6))
    win = 1 if outcome == "TP" or (outcome == "TIMEOUT" and net_return_pct > 0) else 0

    return {
        "outcome": outcome,
        "win": win,
        "entry_price": real_entry,
        "exit_price": exit_price,
        "net_return_pct": net_return_pct,
        "pnl_atr": pnl_atr,
        "mfe_atr": mfe_atr,
        "mae_atr": mae_atr,
        "bars_held": exit_idx - entry_idx,
    }


async def main():
    print("=" * 100)
    print("PHASE 5.1: RESEARCH & ARCHITECTURE AUDIT — TRADING CONTEXT & SIGNAL INTEGRATION")
    print("=" * 100)

    ltf_step = _resolve_timeframe_step_seconds(interval_str=BASE_TF, default_step=900)
    htf_step = _resolve_timeframe_step_seconds(interval_str=HTF_TF, default_step=3600)

    # Containers for experimental groups
    group_all_signals = []          # Group 1: Baseline raw LONG signals
    group_htf_aligned = []          # Group 2a: LONG signals with HTF ALIGNED
    group_htf_against = []          # Group 2b: LONG signals with HTF AGAINST
    group_htf_neutral = []          # Group 2c: LONG signals with HTF NEUTRAL
    group_risk_filtered = []        # Group 3: Strict Risk Filtered (No AGAINST, No COMPRESSION, No Resistance Headwind)
    group_retest_entries = []       # Group 5: Scenario E — Confirmed Breakout-Retest entries
    scenario_b_headwind = []        # Scenario B: LONG signals with direct Resistance Headwind <= 1.0 ATR
    scenario_b_open_space = []      # Scenario B control: LONG signals with Resistance Headwind > 2.5 ATR or none

    target_coins = await resolve_research_coins(min_volume_usd=5_000_000, top_n=10)
    print(f"Universally discovered {len(target_coins)} active perpetuals: {target_coins}")

    for coin in target_coins:
        print(f"\nLoading multi-timeframe candle datasets for {coin}...")
        ds_ltf = await get_single_dataset(coin=coin, timeframe=BASE_TF, limit=1200)
        ds_htf = await get_single_dataset(coin=coin, timeframe=HTF_TF, limit=600)
        c_ltf = ds_ltf["candles"]
        c_htf = ds_htf["candles"]

        if not c_ltf or len(c_ltf) < 100 or not c_htf or len(c_htf) < 40:
            print(f"  [{coin}] Insufficient candle data.")
            continue

        n_ltf = len(c_ltf)

        # Walk-forward Point-in-Time bar-by-bar
        for t_idx in range(50, n_ltf - HORIZON_BARS):
            curr_c = c_ltf[t_idx]
            curr_time = curr_c["time"]
            candles_up_to_t = c_ltf[:t_idx + 1]
            atr = calculate_atr(candles_up_to_t, 14)
            if atr <= 0: continue

            # Strict PIT HTF candles: closed at or before current bar close
            # (t_htf + htf_step <= curr_time + ltf_step)
            eval_time = curr_time + ltf_step
            pit_htf = [c for c in c_htf if int(c.get("close_time") or (c["time"] + htf_step)) <= eval_time]
            if len(pit_htf) < 20: continue

            htf_struct = analyze_market_structure(pit_htf)
            htf_trend = htf_struct.get("trend", "NEUTRAL")

            # --- Detect Potential Local Resistance Trendlines (for Scenario B Headwind) ---
            swings = find_swings_for_trendlines(candles_up_to_t, interval=BASE_TF, atr=atr)
            highs = swings["highs"][-6:]
            lows = swings["lows"][-6:]

            nearest_res_dist_atr = 999.0
            for i in range(len(highs) - 1):
                for j in range(i + 1, len(highs)):
                    p1, p2 = highs[i], highs[j]
                    bar_dist = p2["index"] - p1["index"]
                    if bar_dist < 4 or p1["price"] <= p2["price"]: continue
                    slope = (p2["price"] - p1["price"]) / bar_dist
                    diff = p1["price"] - p2["price"]
                    if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr: continue
                    # Line price at current bar
                    line_p = p1["price"] + slope * (t_idx - p1["index"])
                    if line_p > curr_c["close"]:
                        dist_atr = (line_p - curr_c["close"]) / atr
                        if dist_atr < nearest_res_dist_atr:
                            nearest_res_dist_atr = dist_atr

            # Local Volatility Compression
            sub5 = candles_up_to_t[max(0, t_idx - 5):]
            sub20 = candles_up_to_t[max(0, t_idx - 20):]
            a5 = calculate_atr(sub5, 5)
            a20 = calculate_atr(sub20, 20)
            comp_ratio = (a5 / a20) if a20 > 0 else 1.0
            is_compression = comp_ratio < DEFAULT_COMPRESSION_THRESHOLD

            # --- Detect Candidate LONG Signals on this bar ---
            # 1. Bullish Support Sweep / Wick Rejection:
            is_long_sweep = False
            for p in lows:
                # Price dipped below recent low and closed back above
                if curr_c["low"] < p["price"] and curr_c["close"] > p["price"] and (curr_c["close"] - p["price"]) <= 0.6 * atr:
                    is_long_sweep = True
                    break

            # 2. Bullish FVG Mitigation:
            fvgs = detect_and_track_fvgs(candles_up_to_t, interval=BASE_TF, symbol=coin)
            is_long_fvg_test = False
            for f in fvgs:
                if f["type"] == "BULLISH" and f["mitigation_status"] != "FULLY MITIGATED":
                    if f["lower_price"] <= curr_c["close"] <= f["upper_price"]:
                        is_long_fvg_test = True
                        break

            # 3. Support Trendline Touch / Bounce (Scenario A):
            is_support_tl_touch = False
            support_tl_q = 0.0
            for i in range(len(lows) - 1):
                for j in range(i + 1, len(lows)):
                    p1, p2 = lows[i], lows[j]
                    bar_dist = p2["index"] - p1["index"]
                    if bar_dist < 4 or p2["price"] <= p1["price"]: continue
                    slope = (p2["price"] - p1["price"]) / bar_dist
                    diff = p2["price"] - p1["price"]
                    if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr: continue
                    line_p = p1["price"] + slope * (t_idx - p1["index"])
                    # Contact zone: within 0.35 ATR and close >= line - 0.25 ATR
                    if abs(curr_c["low"] - line_p) <= 0.35 * atr and curr_c["close"] >= line_p - 0.25 * atr:
                        is_support_tl_touch = True
                        q, _ = calculate_structural_quality(candles_up_to_t, p1, p2, slope, atr, [], False)
                        support_tl_q = q
                        break

            # 4. Breakout-Retest Setup (Scenario E):
            is_breakout_retest = False
            for i in range(len(highs) - 1):
                for j in range(i + 1, len(highs)):
                    p1, p2 = highs[i], highs[j]
                    bar_dist = p2["index"] - p1["index"]
                    if bar_dist < 4 or p1["price"] <= p2["price"]: continue
                    slope = (p2["price"] - p1["price"]) / bar_dist
                    diff = p1["price"] - p2["price"]
                    if diff < 0.35 * atr or abs(slope) < 0.02 * atr or abs(slope) > 1.6 * atr: continue
                    line_p = p1["price"] + slope * (t_idx - p1["index"])
                    # Retest: price previously closed above line (breakout) and is now testing line from above
                    prev_c = candles_up_to_t[t_idx - 1]
                    prev_lp = p1["price"] + slope * (t_idx - 1 - p1["index"])
                    if prev_c["close"] > prev_lp + 0.25 * atr:
                        # Now testing from above:
                        if -0.25 * atr <= (curr_c["close"] - line_p) <= 0.40 * atr and curr_c["low"] <= line_p + 0.35 * atr:
                            is_breakout_retest = True
                            break

            # --- Evaluate Signal Execution ---
            # Any valid baseline LONG trigger:
            is_baseline_long = is_long_sweep or is_long_fvg_test or (is_support_tl_touch and support_tl_q >= 80)

            if is_baseline_long:
                htf_ctx = "ALIGNED" if htf_trend == "BULLISH" else ("AGAINST_HTF" if htf_trend == "BEARISH" else "NEUTRAL")

                # Simulate trade forward
                trade = simulate_forward_trade(
                    candles=c_ltf,
                    entry_idx=t_idx,
                    entry_price=curr_c["close"],
                    atr=atr,
                )
                trade["coin"] = coin
                trade["time"] = curr_time
                trade["htf_context"] = htf_ctx
                trade["compression"] = is_compression
                trade["res_headwind_atr"] = nearest_res_dist_atr

                # Group 1: All Baseline Signals
                group_all_signals.append(trade)

                # Group 2: HTF Breakdown
                if htf_ctx == "ALIGNED":
                    group_htf_aligned.append(trade)
                elif htf_ctx == "AGAINST_HTF":
                    group_htf_against.append(trade)
                else:
                    group_htf_neutral.append(trade)

                # Scenario B: Resistance Headwind Proximity
                if nearest_res_dist_atr <= 1.0:
                    scenario_b_headwind.append(trade)
                elif nearest_res_dist_atr >= 2.5:
                    scenario_b_open_space.append(trade)

                # Group 3: Strict Structural Risk Filtered
                # Must be: HTF != AGAINST_HTF, NO Volatility Compression, NO Resistance Headwind <= 1.0 ATR
                if htf_ctx != "AGAINST_HTF" and not is_compression and nearest_res_dist_atr > 1.0:
                    group_risk_filtered.append(trade)

            # Group 5: Scenario E — Breakout / Retest Entries
            if is_breakout_retest and htf_trend != "BEARISH":
                retest_trade = simulate_forward_trade(
                    candles=c_ltf,
                    entry_idx=t_idx,
                    entry_price=curr_c["close"],
                    atr=atr,
                )
                retest_trade["coin"] = coin
                retest_trade["time"] = curr_time
                group_retest_entries.append(retest_trade)

    # --- STATISTICAL REPORTING & SYNTHESIS ---
    def calc_group_metrics(trades: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        n = len(trades)
        if n == 0:
            return {"name": name, "N": 0}
        wins = sum(t["win"] for t in trades)
        p_win, win_l, win_h = wilson_score_ci(wins, n)
        mean_exp, exp_l, exp_h = clustered_bootstrap_expectancy(trades)

        mean_mfe = sum(t["mfe_atr"] for t in trades) / n
        mean_mae = sum(t["mae_atr"] for t in trades) / n

        # Profit factor: sum wins / sum losses in ATR
        win_sum = sum(t["pnl_atr"] for t in trades if t["pnl_atr"] > 0)
        loss_sum = abs(sum(t["pnl_atr"] for t in trades if t["pnl_atr"] < 0))
        pf = (win_sum / max(loss_sum, 1e-6)) if loss_sum > 0 else 99.0

        # Max drawdown across trade series (running cumulative PnL drawdown)
        cum_pnl = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cum_pnl += t["pnl_atr"]
            if cum_pnl > peak: peak = cum_pnl
            dd = peak - cum_pnl
            if dd > max_dd: max_dd = dd

        return {
            "name": name,
            "N": n,
            "win_rate": p_win,
            "win_ci": (win_l, win_h),
            "expectancy_atr": mean_exp,
            "exp_ci": (exp_l, exp_h),
            "pf": pf,
            "mean_mfe": mean_mfe,
            "mean_mae": mean_mae,
            "max_dd_atr": max_dd,
        }

    results = [
        calc_group_metrics(group_all_signals, "Group 1: Raw Baseline LONG Signals"),
        calc_group_metrics(group_htf_aligned, "Group 2a: HTF ALIGNED (Bullish HTF)"),
        calc_group_metrics(group_htf_against, "Group 2b: HTF AGAINST (Bearish HTF)"),
        calc_group_metrics(group_htf_neutral, "Group 2c: HTF NEUTRAL (Consolidation)"),
        calc_group_metrics(scenario_b_headwind, "Scenario B: Resistance Headwind (Dist <= 1.0 ATR)"),
        calc_group_metrics(scenario_b_open_space, "Scenario B Control: Open Space (Dist >= 2.5 ATR)"),
        calc_group_metrics(group_risk_filtered, "Group 3: Full Structural Risk Filtered"),
        calc_group_metrics(group_retest_entries, "Group 5: Scenario E (Breakout-Retest Entries)"),
    ]

    print("\n" + "=" * 105)
    print(f"{'Group / Scenario':<42} | {'N':<5} | {'Win Rate (95% CI)':<22} | {'Expectancy (ATR)':<20} | {'PF':<5} | {'MFE':<5} | {'MAE':<5} | {'MaxDD'}")
    print("-" * 105)
    for r in results:
        if r["N"] == 0: continue
        wr = f"{r['win_rate']*100:4.1f}% [{r['win_ci'][0]*100:4.1f}-{r['win_ci'][1]*100:4.1f}%]"
        exp = f"{r['expectancy_atr']:+.3f} [{r['exp_ci'][0]:+.2f}, {r['exp_ci'][1]:+.2f}]"
        print(f"{r['name']:<42} | {r['N']:<5} | {wr:<22} | {exp:<20} | {r['pf']:<5.2f} | {r['mean_mfe']:<5.2f} | {r['mean_mae']:<5.2f} | {r['max_dd_atr']:<5.1f}")
    print("=" * 105)

    # Filter impact calculation
    n_base = len(group_all_signals)
    n_filt = len(group_risk_filtered)
    rejection_rate = (n_base - n_filt) / n_base * 100.0 if n_base > 0 else 0.0
    print(f"\nFILTERING IMPACT SUMMARY:")
    print(f"  Raw Baseline Signals:        {n_base}")
    print(f"  Filtered Signals:            {n_filt}")
    print(f"  Rejection Rate (Filtered):   {rejection_rate:.1f}%")

    base_exp = results[0]["expectancy_atr"]
    filt_exp = results[6]["expectancy_atr"]
    exp_improvement = (filt_exp - base_exp)
    print(f"  Expectancy Improvement:      {exp_improvement:+.3f} ATR / trade")
    print("=" * 105)


if __name__ == "__main__":
    asyncio.run(main())
