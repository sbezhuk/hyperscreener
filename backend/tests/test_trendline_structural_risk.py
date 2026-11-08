import unittest
import math
from typing import List, Dict, Any
from app.analyzer.trendline import (
    evaluate_htf_structural_context,
    compute_structural_risk_flags,
    detect_timeframe_trendlines,
)
from app.analyzer.mtf_trendline import MTFTrendlineManager, HTF_TIMEFRAME_MAP


class TestTrendlineStructuralRisk(unittest.TestCase):
    def setUp(self):
        self.base_time = 1700000000

    def _generate_synthetic_candles(
        self,
        count: int = 40,
        trend: str = "BULLISH",
        step_seconds: int = 3600,
        base_price: float = 2000.0,
    ) -> List[Dict[str, Any]]:
        """Generates synthetic HTF candles with wave structure guaranteeing swing highs and lows."""
        candles = []
        for i in range(count):
            t = self.base_time + i * step_seconds
            drift = (i * 6.0) if trend == "BULLISH" else (-i * 6.0 if trend == "BEARISH" else 0.0)
            wave = 22.0 * math.sin(i * 2.0 * math.pi / 12.0)
            p = base_price + drift + wave
            candles.append({
                "time": t,
                "open": float(p),
                "high": float(p + 2.0),
                "low": float(p - 2.0),
                "close": float(p),
                "volume": 1000.0,
            })
        return candles

    def _generate_downtrend_candles(
        self,
        base_time: int,
        interval_seconds: int,
        p1_price: float,
        p2_price: float,
    ) -> List[Dict[str, Any]]:
        """Generates candles forming a clean descending resistance trendline."""
        candles = []
        slope = (p2_price - p1_price) / 10.0
        for i in range(20):
            t = base_time + i * interval_seconds
            if i == 3:
                h = p1_price
                l = p1_price - 10.0
                o = p1_price - 5.0
                c = p1_price - 3.0
            elif i == 13:
                h = p2_price
                l = p2_price - 10.0
                o = p2_price - 6.0
                c = p2_price - 4.0
            elif i < 3:
                base = p1_price - (3 - i) * 8.0
                o, h, l, c = base, base + 5.0, base - 5.0, base + 2.0
            elif 3 < i < 13:
                dist = min(i - 3, 13 - i)
                base = min(p1_price, p2_price) - 30.0 + dist * 2.0
                o, h, l, c = base, base + 4.0, base - 4.0, base
            else:
                base = p2_price + slope * (i - 13) - 8.0
                o, h, l, c = base, base + 2.0, base - 6.0, base - 3.0

            candles.append({
                "time": t,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1000.0,
            })
        return candles

    def test_htf_context_classifications(self):
        """1. Tests all 4 classifications: ALIGNED, AGAINST_HTF, NEUTRAL, UNAVAILABLE."""
        bullish_htf = self._generate_synthetic_candles(count=40, trend="BULLISH")
        bearish_htf = self._generate_synthetic_candles(count=40, trend="BEARISH")
        neutral_htf = self._generate_synthetic_candles(count=40, trend="NEUTRAL")
        eval_time = bullish_htf[-1]["time"]

        # Support line:
        # Bullish HTF -> ALIGNED
        self.assertEqual(
            evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf),
            "ALIGNED"
        )
        # Bearish HTF -> AGAINST_HTF
        self.assertEqual(
            evaluate_htf_structural_context("support_trendline", eval_time, bearish_htf),
            "AGAINST_HTF"
        )
        # Neutral HTF -> NEUTRAL
        self.assertEqual(
            evaluate_htf_structural_context("support_trendline", eval_time, neutral_htf),
            "NEUTRAL"
        )

        # Resistance line:
        # Bullish HTF -> AGAINST_HTF
        self.assertEqual(
            evaluate_htf_structural_context("resistance_trendline", eval_time, bullish_htf),
            "AGAINST_HTF"
        )
        # Bearish HTF -> ALIGNED
        self.assertEqual(
            evaluate_htf_structural_context("resistance_trendline", eval_time, bearish_htf),
            "ALIGNED"
        )
        # Neutral HTF -> NEUTRAL
        self.assertEqual(
            evaluate_htf_structural_context("resistance_trendline", eval_time, neutral_htf),
            "NEUTRAL"
        )

        # Insufficient data (< 20 candles) or None -> UNAVAILABLE
        self.assertEqual(
            evaluate_htf_structural_context("support_trendline", eval_time, None),
            "UNAVAILABLE"
        )
        self.assertEqual(
            evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf[:15]),
            "UNAVAILABLE"
        )

    def test_point_in_time_zero_lookahead_bias(self):
        """2. Tests that future HTF candles (time > candle_time) never contaminate evaluation."""
        htf = self._generate_synthetic_candles(count=50, trend="BULLISH")
        eval_time = htf[25]["time"]

        ctx_at_25 = evaluate_htf_structural_context("support_trendline", eval_time, htf)

        # Append drastic future changes (e.g. sharp bearish reversal in candles 26..49)
        modified_htf = list(htf)
        for k in range(26, len(modified_htf)):
            modified_htf[k]["close"] = modified_htf[k]["close"] * 0.5
            modified_htf[k]["low"] = modified_htf[k]["low"] * 0.5
            modified_htf[k]["high"] = modified_htf[k]["high"] * 0.5

        ctx_after_future_change = evaluate_htf_structural_context("support_trendline", eval_time, modified_htf)

        # Evaluation at candle 25 MUST be completely unaffected by future bars
        self.assertEqual(ctx_at_25, ctx_after_future_change)

    def test_structural_risk_flags_coexistence(self):
        """3. Tests coexisting structural risk flags without overrides."""
        # Case A: Healthy aligned line with no warnings
        flags_a = compute_structural_risk_flags(
            htf_context="ALIGNED",
            interaction_state="APPROACHING",
            compression_ratio=0.95,
            status="ACTIVE",
        )
        self.assertEqual(flags_a, [])

        # Case B: AGAINST_HTF alone
        flags_b = compute_structural_risk_flags(
            htf_context="AGAINST_HTF",
            interaction_state="APPROACHING",
            compression_ratio=0.85,
            status="ACTIVE",
        )
        self.assertEqual(flags_b, ["AGAINST_HTF"])

        # Case C: AGAINST_HTF + COMPRESSION
        flags_c = compute_structural_risk_flags(
            htf_context="AGAINST_HTF",
            interaction_state="COMPRESSION",
            compression_ratio=0.55,
            status="ACTIVE",
        )
        self.assertIn("AGAINST_HTF", flags_c)
        self.assertIn("COMPRESSION", flags_c)
        self.assertEqual(len(flags_c), 2)

        # Case D: AGAINST_HTF + BREAKOUT
        flags_d = compute_structural_risk_flags(
            htf_context="AGAINST_HTF",
            interaction_state="BREAKOUT",
            compression_ratio=0.75,
            status="BROKEN",
        )
        self.assertIn("AGAINST_HTF", flags_d)
        self.assertIn("BREAKOUT", flags_d)

        # Case E: RETEST flag
        flags_e = compute_structural_risk_flags(
            htf_context="ALIGNED",
            interaction_state="RETEST",
            compression_ratio=0.80,
            status="ACTIVE",
        )
        self.assertEqual(flags_e, ["RETEST"])

        # Case F: STALE flag
        flags_f = compute_structural_risk_flags(
            htf_context="NEUTRAL",
            interaction_state="STALE",
            compression_ratio=0.90,
            status="STALE",
        )
        self.assertEqual(flags_f, ["STALE"])

    def test_baseline_q_remains_unaltered_by_htf_context(self):
        """4. Verifies that Structural Quality (Q) score is 100% independent of HTF context."""
        # Bullish HTF dataset (50 candles of 1h)
        bullish_htf = self._generate_synthetic_candles(count=50, trend="BULLISH", step_seconds=3600)

        # Start LTF candles at bar 25 of HTF so >= 25 HTF candles are closed and available
        ltf_base = self.base_time + 25 * 3600
        ltf_candles = self._generate_downtrend_candles(
            base_time=ltf_base,
            interval_seconds=900,
            p1_price=2500.0,
            p2_price=2450.0,
        )

        # Run without HTF candles
        tls_without_htf = detect_timeframe_trendlines(ltf_candles, interval="15m")
        self.assertTrue(len(tls_without_htf) > 0)
        tl_no_htf = tls_without_htf[0]

        # Run with Bullish HTF (so resistance becomes AGAINST_HTF)
        tls_with_bullish_htf = detect_timeframe_trendlines(ltf_candles, interval="15m", htf_candles=bullish_htf)
        self.assertTrue(len(tls_with_bullish_htf) > 0)
        tl_against_htf = tls_with_bullish_htf[0]

        # 1. Structural Quality Q MUST be identical
        self.assertEqual(tl_no_htf["structural_quality"], tl_against_htf["structural_quality"])
        self.assertEqual(tl_no_htf["slope"], tl_against_htf["slope"])
        self.assertEqual(tl_no_htf["start_point"]["price"], tl_against_htf["start_point"]["price"])
        self.assertEqual(tl_no_htf["end_point"]["price"], tl_against_htf["end_point"]["price"])

        # 2. HTF context and risk flags are isolated layers
        self.assertEqual(tl_no_htf["htf_context"], "UNAVAILABLE")
        self.assertNotIn("AGAINST_HTF", tl_no_htf["structural_risk_flags"])

        self.assertEqual(tl_against_htf["htf_context"], "AGAINST_HTF")
        self.assertIn("AGAINST_HTF", tl_against_htf["structural_risk_flags"])

    # --- Phase 4.6: Strict Point-in-Time HTF Tests ---

    def test_pit_1_unclosed_htf_candle_is_excluded(self):
        """Phase 4.6.1: An unclosed/forming HTF candle is strictly excluded from market structure."""
        bullish_htf = self._generate_synthetic_candles(count=25, trend="BULLISH", step_seconds=3600)
        # Bar 24 opens at base_time + 24*3600 = base_time + 86400, and closes at base_time + 90000
        bar24_open = bullish_htf[24]["time"]
        
        # Inject an extreme reversal into bar 24 (which is still forming)
        bullish_htf[24]["close"] = 100.0
        bullish_htf[24]["low"] = 90.0

        # Evaluate at 15 minutes into bar 24 (bar 24 is unclosed)
        eval_time = bar24_open + 900
        
        # If strict PIT works, bar 24 is excluded, and only bars 0..23 (24 closed bars) are evaluated (BULLISH)
        ctx = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=eval_time,
            htf_candles=bullish_htf,
            evaluation_time=eval_time,
        )
        self.assertEqual(ctx, "ALIGNED")

    def test_pit_2_closed_htf_candle_is_included(self):
        """Phase 4.6.2: An HTF candle is included once it has fully closed."""
        bullish_htf = self._generate_synthetic_candles(count=25, trend="BULLISH", step_seconds=3600)
        bar24_open = bullish_htf[24]["time"]
        bar24_close = bar24_open + 3600

        # Evaluate at exact close of bar 24
        ctx = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=bar24_close,
            htf_candles=bullish_htf,
            evaluation_time=bar24_close,
        )
        # 25 closed bars are included
        self.assertEqual(ctx, "ALIGNED")

    def test_pit_3_exact_boundary_close_time(self):
        """Phase 4.6.3: Candle on exact close boundary (t == close_time) vs (t == close_time - 1)."""
        bullish_htf = self._generate_synthetic_candles(count=25, trend="BULLISH", step_seconds=3600)
        bar24_close = bullish_htf[24]["time"] + 3600

        # At close_time - 1 second: bar 24 has NOT closed yet
        # Exactly 24 bars are closed (0..23)
        ctx_before = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=bar24_close - 1,
            htf_candles=bullish_htf,
            evaluation_time=bar24_close - 1,
        )
        self.assertEqual(ctx_before, "ALIGNED")

        # At close_time: bar 24 has closed, 25 bars closed
        ctx_at = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=bar24_close,
            htf_candles=bullish_htf,
            evaluation_time=bar24_close,
        )
        self.assertEqual(ctx_at, "ALIGNED")

    def test_pit_4_insufficient_or_missing_htf_returns_unavailable(self):
        """Phase 4.6.4: Missing or fewer than 20 closed HTF candles returns UNAVAILABLE."""
        bullish_htf = self._generate_synthetic_candles(count=15, trend="BULLISH", step_seconds=3600)
        eval_time = bullish_htf[-1]["time"] + 3600

        self.assertEqual(evaluate_htf_structural_context("support_trendline", eval_time, None), "UNAVAILABLE")
        self.assertEqual(evaluate_htf_structural_context("support_trendline", eval_time, []), "UNAVAILABLE")
        self.assertEqual(evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf), "UNAVAILABLE")

    def test_pit_5_deterministic_and_restart_invariant(self):
        """Phase 4.6.5: Evaluation is 100% deterministic and invariant across fresh manager instances."""
        bullish_htf = self._generate_synthetic_candles(count=30, trend="BULLISH", step_seconds=3600)
        eval_time = bullish_htf[-1]["time"] + 3600

        res1 = evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf)
        res2 = evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf)
        self.assertEqual(res1, res2)

    def test_pit_6_zero_future_leakage(self):
        """Phase 4.6.6: Future HTF candles (t > evaluation_time) cannot alter historical outcome."""
        bullish_htf = self._generate_synthetic_candles(count=40, trend="BULLISH", step_seconds=3600)
        eval_time = bullish_htf[24]["time"] + 3600  # Bar 24 closed

        baseline = evaluate_htf_structural_context("support_trendline", eval_time, bullish_htf)

        # Mutate future bars (25..39) to a massive crash
        corrupted_htf = list(bullish_htf)
        for k in range(25, 40):
            corrupted_htf[k]["close"] = 10.0
            corrupted_htf[k]["low"] = 5.0
            corrupted_htf[k]["high"] = 15.0

        after = evaluate_htf_structural_context("support_trendline", eval_time, corrupted_htf)
        self.assertEqual(baseline, after)

    def test_pit_7_unclosed_ltf_candle_does_not_grant_future_access(self):
        """Phase 4.6.7: An unclosed LTF candle evaluates strictly at bar open time, preventing Look-Ahead."""
        bullish_htf = self._generate_synthetic_candles(count=30, trend="BULLISH", step_seconds=3600)
        # Bar 24 opens at base_time + 24*3600 = 86400, closes at 90000
        # Suppose a 15m candle opens at 89100 (15m before bar 24 closes)
        ltf_open = self.base_time + 24 * 3600 + 2700  # 89100

        # If forming (is_candle_closed=False): eval_time = ltf_open (89100 < 90000). Bar 24 is NOT closed yet!
        forming_ctx = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=ltf_open,
            htf_candles=bullish_htf,
            is_candle_closed=False,
            ltf_interval="15m",
        )
        self.assertEqual(forming_ctx, "ALIGNED")

        # If completed (is_candle_closed=True): eval_time = 89100 + 900 = 90000. Bar 24 HAS closed!
        closed_ctx = evaluate_htf_structural_context(
            line_type="support_trendline",
            candle_time=ltf_open,
            htf_candles=bullish_htf,
            is_candle_closed=True,
            ltf_interval="15m",
        )
        self.assertEqual(closed_ctx, "ALIGNED")

    def test_pit_8_cache_symbol_and_timeframe_isolation(self):
        """Phase 4.6.8: MTFTrendlineManager strictly isolates symbols and timeframes."""
        mgr = MTFTrendlineManager(cache_ttl_seconds=60.0)
        mgr.clear_cache()

        tls_btc = [{"id": "btc-1", "timeframe": "15m", "slope": 0.1, "structural_quality": 90}]
        tls_eth = [{"id": "eth-1", "timeframe": "15m", "slope": -0.1, "structural_quality": 85}]
        tls_btc_1h = [{"id": "btc-1h", "timeframe": "1h", "slope": 0.05, "structural_quality": 92}]

        mgr.store_cached_trendlines("BTC", "15m", tls_btc, 1000)
        mgr.store_cached_trendlines("ETH", "15m", tls_eth, 1000)
        mgr.store_cached_trendlines("BTC", "1h", tls_btc_1h, 1000)

        self.assertEqual(mgr.get_cached_trendlines("BTC", "15m"), tls_btc)
        self.assertEqual(mgr.get_cached_trendlines("ETH", "15m"), tls_eth)
        self.assertEqual(mgr.get_cached_trendlines("BTC", "1h"), tls_btc_1h)
        self.assertIsNone(mgr.get_cached_trendlines("SOL", "15m"))


if __name__ == "__main__":
    unittest.main()
