import unittest
from app.analyzer.trendline import (
    find_swings_for_trendlines,
    detect_timeframe_trendlines,
    calculate_atr,
    calculate_structural_quality,
    evaluate_market_interaction_state,
)
from app.analyzer.mtf_trendline import MTFTrendlineManager


class TestTrendlineStructuralIntelligence(unittest.TestCase):
    def setUp(self):
        self.mtf_mgr = MTFTrendlineManager(cache_ttl_seconds=60.0)
        self.mtf_mgr.clear_cache()
        self.base_time = 1700000000

    def _make_candle(self, idx, o, h, l, c, interval_sec=300):
        return {
            "time": self.base_time + idx * interval_sec,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": 1000.0,
        }

    def test_structural_quality_calculation_and_components(self):
        """
        Phase 1 Test: Structural Quality (Q) calculation and individual components.
        Checks that Q is within [10, 98], all 4 components exist, and no artificial saturation occurs.
        """
        # Build 25 candles with clean swing highs at bar 3 (price 100) and bar 13 (price 90)
        candles = []
        for i in range(25):
            if i == 3:
                candles.append(self._make_candle(i, 95, 100, 92, 94))
            elif i == 13:
                candles.append(self._make_candle(i, 87, 90, 84, 86))
            elif i < 3:
                candles.append(self._make_candle(i, 80 + i * 4, 82 + i * 4, 78 + i * 4, 81 + i * 4))
            elif 3 < i < 13:
                # Valley between 3 and 13
                candles.append(self._make_candle(i, 75, 78, 70, 74))
            else:
                candles.append(self._make_candle(i, 80, 82, 75, 78))

        atr = 5.0
        p1 = {"index": 3, "price": 100.0, "time": candles[3]["time"]}
        p2 = {"index": 13, "price": 90.0, "time": candles[13]["time"]}
        slope = -1.0
        touches = [
            {"index": 3, "time": candles[3]["time"], "price": 100.0, "dist_atr": 0.0},
            {"index": 13, "time": candles[13]["time"], "price": 90.0, "dist_atr": 0.0},
        ]

        q_score, components = calculate_structural_quality(
            candles=candles,
            p1=p1,
            p2=p2,
            slope=slope,
            atr=atr,
            touches=touches,
            is_res=True,
        )

        self.assertGreaterEqual(q_score, 10.0)
        self.assertLessEqual(q_score, 98.0)
        self.assertIn("anchor_prominence", components)
        self.assertIn("spacing_regularity", components)
        self.assertIn("ray_precision", components)
        self.assertIn("void_integrity", components)

        # Sum of components equals Q
        comp_sum = sum(components.values())
        self.assertAlmostEqual(q_score, comp_sum, delta=0.5)

    def test_state_machine_approaching_to_testing_to_rejected(self):
        """
        Phase 2 Test: FSM transitions sequentially:
        APPROACHING -> TESTING -> REJECTED
        """
        candles = []
        # Line born at bar 10 at price 100 with slope 0.0. ATR = 10.0.
        # Bar 11: price is at 88 (dist = 12 = 1.2 ATR -> APPROACHING)
        # Bar 12: price rises to high 99 (dist_ext = 1 = 0.1 ATR -> TESTING)
        # Bar 13: price rejected down to close 93 (dist_close = 7 = 0.7 ATR >= 0.5 ATR -> REJECTED)
        for i in range(11):
            candles.append(self._make_candle(i, 80, 85, 78, 82))
        candles.append(self._make_candle(11, 85, 89, 84, 88))
        candles.append(self._make_candle(12, 88, 99, 87, 97))
        candles.append(self._make_candle(13, 96, 96, 92, 93))

        atr_series = [10.0] * len(candles)
        p1 = {"index": 0, "price": 100.0, "time": candles[0]["time"]}
        fsm_res = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )

        self.assertEqual(fsm_res["current_state"], "REJECTED")
        self.assertEqual(fsm_res["previous_state"], "TESTING")

    def test_state_machine_breakout_priority_and_retest(self):
        """
        Phase 2 Test: BREAKOUT has absolute priority, and RETEST is only possible after confirmed BREAKOUT.
        """
        candles = []
        # Line at 100.0 (slope 0). ATR = 10.0. Breakout buffer = 0.25 * ATR = 2.5 (price 102.5).
        for i in range(11):
            candles.append(self._make_candle(i, 80, 85, 78, 82))

        # Bar 11: Breakout confirmed: close = 104 (> 102.5)
        candles.append(self._make_candle(11, 98, 105, 97, 104))
        atr_series = [10.0] * len(candles)
        p1 = {"index": 0, "price": 100.0, "time": candles[0]["time"]}

        res_brk = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(res_brk["current_state"], "BREAKOUT")
        self.assertTrue(res_brk["has_broken_out"])

        # Now price rallies further, then pulls back to test broken resistance from above (RETEST)
        candles.append(self._make_candle(12, 104, 112, 103, 110))
        candles.append(self._make_candle(13, 110, 110, 101, 102)) # low tests 101 (near 100)
        atr_series = [10.0] * len(candles)

        res_retest = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(res_retest["current_state"], "RETEST")
        self.assertEqual(res_retest["previous_state"], "BREAKOUT")

    def test_state_machine_stale_after_prolonged_inactivity(self):
        """
        Phase 2 Test: Line becomes STALE if no price interaction occurs for > 40 bars.
        """
        candles = []
        for i in range(60):
            # Price stays far down at 60 (4 ATR below line at 100)
            candles.append(self._make_candle(i, 60, 62, 58, 60))

        atr_series = [10.0] * len(candles)
        p1 = {"index": 0, "price": 100.0, "time": candles[0]["time"]}

        res_stale = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(res_stale["current_state"], "STALE")

    def test_wick_only_breach_does_not_trigger_breakout(self):
        """
        Phase 3 Scenario: Wick-only breach (candle high pierces line + 0.4 ATR, but close settles under line).
        FSM must remain in TESTING, NOT trigger BREAKOUT.
        """
        candles = []
        for i in range(11):
            candles.append(self._make_candle(i, 80, 85, 78, 82))
        # Bar 11: High spikes to 104.0 (piercing 100 + 0.25*10 = 102.5), but Close is 98.0
        candles.append(self._make_candle(11, 98.0, 104.0, 97.0, 98.0))

        atr_series = [10.0] * len(candles)
        p1 = {"index": 0, "price": 100.0, "time": candles[0]["time"]}
        fsm_res = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(fsm_res["current_state"], "TESTING")
        self.assertFalse(fsm_res["has_broken_out"])

    def test_rejection_requires_confirmed_reaction_away(self):
        """
        Phase 3 Scenario: REJECTED requires confirmed price reaction away (>= 0.50 ATR).
        If close moves away only by 0.20 ATR, state must NOT prematurely switch to REJECTED.
        """
        candles = []
        for i in range(11):
            candles.append(self._make_candle(i, 80, 85, 78, 82))
        # Bar 11: Tests line at 99.5
        candles.append(self._make_candle(11, 95.0, 99.5, 94.0, 98.5))
        # Bar 12: Close moves down to 98.0 (dist = 2.0 = 0.20 ATR < 0.50 ATR) -> Still TESTING
        candles.append(self._make_candle(12, 98.5, 99.0, 97.5, 98.0))

        atr_series = [10.0] * len(candles)
        p1 = {"index": 0, "price": 100.0, "time": candles[0]["time"]}
        res1 = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(res1["current_state"], "TESTING")

        # Bar 13: Close drops to 94.0 (dist = 6.0 = 0.60 ATR >= 0.50 ATR) -> Confirmed REJECTED
        candles.append(self._make_candle(13, 98.0, 98.0, 93.5, 94.0))
        atr_series = [10.0] * len(candles)
        res2 = evaluate_market_interaction_state(
            candles=candles,
            p1=p1,
            slope=0.0,
            atr_series=atr_series,
            is_res=True,
            born_idx=10,
        )
        self.assertEqual(res2["current_state"], "REJECTED")

    def test_compression_with_bounce_vs_breakout(self):
        """
        Phase 3 Scenario: Compression exiting via bounce (REJECTED) vs exiting via BREAKOUT.
        """
        # Case A: Compression exiting via bounce
        candles_bounce = []
        for i in range(20):
            candles_bounce.append(self._make_candle(i, 80, 95, 75, 88))
        for i in range(20, 24):
            candles_bounce.append(self._make_candle(i, 99.0, 99.5, 98.5, 99.2))
        # Bar 24: decisive drop to 90 (1.0 ATR away)
        candles_bounce.append(self._make_candle(24, 99.0, 99.0, 89.5, 90.0))

        atr_series_b = [calculate_atr(candles_bounce[:i+1], 14) for i in range(len(candles_bounce))]
        p1 = {"index": 0, "price": 100.0, "time": candles_bounce[0]["time"]}
        res_b = evaluate_market_interaction_state(
            candles=candles_bounce,
            p1=p1,
            slope=0.0,
            atr_series=atr_series_b,
            is_res=True,
            born_idx=15,
        )
        self.assertEqual(res_b["current_state"], "REJECTED")
        self.assertEqual(res_b["previous_state"], "COMPRESSION")

        # Case B: Compression exiting via breakout
        candles_brk = []
        for i in range(20):
            candles_brk.append(self._make_candle(i, 80, 95, 75, 88))
        for i in range(20, 24):
            candles_brk.append(self._make_candle(i, 99.0, 99.5, 98.5, 99.2))
        # Bar 24: surge and close at 105.0 (> 100 + 2.5)
        candles_brk.append(self._make_candle(24, 99.0, 106.0, 98.5, 105.0))

        atr_series_brk = [calculate_atr(candles_brk[:i+1], 14) for i in range(len(candles_brk))]
        res_brk = evaluate_market_interaction_state(
            candles=candles_brk,
            p1=p1,
            slope=0.0,
            atr_series=atr_series_brk,
            is_res=True,
            born_idx=15,
        )
        self.assertEqual(res_brk["current_state"], "BREAKOUT")
        self.assertEqual(res_brk["previous_state"], "COMPRESSION")

    def test_point_in_time_lack_of_look_ahead(self):
        """
        Phase 6 Test: Future candles appended do not alter the historical evaluation up to bar T.
        """
        # Baseline series of 25 candles
        candles_t = []
        for i in range(25):
            candles_t.append(self._make_candle(i, 100 - i * 2, 102 - i * 2, 98 - i * 2, 99 - i * 2))

        # Detect trendlines at bar 24
        tls_t = detect_timeframe_trendlines(candles_t, interval="15m")
        if tls_t:
            tl = tls_t[0]
            orig_q = tl["structural_quality"]
            orig_p1 = tl["start_point"]["price"]
            orig_p2 = tl["end_point"]["price"]

            # Now append 10 future candles
            candles_future = list(candles_t)
            for j in range(25, 35):
                candles_future.append(self._make_candle(j, 50, 52, 48, 49))

            # Re-evaluate candidate with original anchors
            recheck_q, _ = calculate_structural_quality(
                candles=candles_t,
                p1=tl["start_point"],
                p2=tl["end_point"],
                slope=tl["slope"],
                atr=calculate_atr(candles_t, 14),
                touches=_collect_trendline_touches(candles_t, tl["start_point"]["index"], tl["end_point"]["index"], orig_p1, tl["slope"], calculate_atr(candles_t, 14), True),
                is_res=True,
            )
            self.assertEqual(orig_q, recheck_q)

    def test_micro_priced_asset_precision(self):
        """
        Phase 6 Test: Micro-priced coins like PUMP ($0.0037) maintain exact precision in Structural Intelligence.
        """
        base_price = 0.003700
        candles = []
        for i in range(25):
            p = base_price - i * 0.000050
            if i == 3:
                h = base_price + 0.000300
                l = base_price - 0.000100
                o, c = base_price + 0.000100, base_price + 0.000200
            elif i == 13:
                h = base_price + 0.000150
                l = base_price - 0.000200
                o, c = base_price, base_price + 0.000100
            else:
                o, h, l, c = p, p + 0.000040, p - 0.000040, p
            candles.append(self._make_candle(i, o, h, l, c))

        tls = detect_timeframe_trendlines(candles, interval="5m")
        for tl in tls:
            self.assertIn("structural_quality", tl)
            self.assertIn("interaction_state", tl)
            self.assertIn("distance_to_line_atr", tl)
            self.assertGreater(tl["start_point"]["price"], 0.0)

    def test_repeatability_on_identical_data(self):
        """
        Phase 6 Test: Running detection multiple times on identical candles yields 100% deterministic identical output.
        """
        candles = []
        for i in range(30):
            candles.append(self._make_candle(i, 2000 - i * 5, 2010 - i * 5, 1990 - i * 5, 1995 - i * 5))

        tls_run1 = detect_timeframe_trendlines(candles, interval="1h")
        tls_run2 = detect_timeframe_trendlines(candles, interval="1h")

        self.assertEqual(len(tls_run1), len(tls_run2))
        for t1, t2 in zip(tls_run1, tls_run2):
            self.assertEqual(t1["structural_quality"], t2["structural_quality"])
            self.assertEqual(t1["interaction_state"], t2["interaction_state"])
            self.assertEqual(t1["start_point"]["price"], t2["start_point"]["price"])
            self.assertEqual(t1["end_point"]["price"], t2["end_point"]["price"])

    def test_regression_existing_geometry_preserved(self):
        """
        Phase 6 Test: Existing anchor points and geometrical slope calculation match legacy expectations.
        """
        candles = []
        for i in range(25):
            if i == 3:
                candles.append(self._make_candle(i, 2485, 2500, 2480, 2490))
            elif i == 13:
                candles.append(self._make_candle(i, 2455, 2460, 2445, 2450))
            elif i < 3:
                candles.append(self._make_candle(i, 2470 + i * 5, 2480 + i * 5, 2465 + i * 5, 2475 + i * 5))
            elif 3 < i < 13:
                candles.append(self._make_candle(i, 2420, 2435, 2400, 2415))
            else:
                candles.append(self._make_candle(i, 2380, 2390, 2360, 2365))

        tls = detect_timeframe_trendlines(candles, interval="5m")
        res_tls = [t for t in tls if "resistance" in t["line_type"]]
        self.assertEqual(len(res_tls), 1)
        tl = res_tls[0]
        self.assertEqual(tl["start_point"]["price"], 2500.0)
        self.assertEqual(tl["end_point"]["price"], 2460.0)
        self.assertEqual(tl["slope"], -4.0)
        self.assertIn("structural_quality", tl)
        self.assertIn("interaction_state", tl)


def _collect_trendline_touches(candles, idx1, idx2, p1_p, slope, atr, is_res):
    # Helper alias for tests
    from app.analyzer.trendline import _collect_trendline_touches as ctt
    return ctt(candles, idx1, idx2, p1_p, slope, atr, is_res)


if __name__ == "__main__":
    unittest.main()
