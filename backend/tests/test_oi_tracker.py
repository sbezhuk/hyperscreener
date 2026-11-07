import unittest
import time
from app.analyzer.oi_tracker import OITracker, OITrackerManager, OISnapshot


class TestOITracker(unittest.TestCase):

    def setUp(self):
        self.tracker = OITracker(coin="ETH", max_history_seconds=7200, stale_threshold_seconds=60)

    def test_record_snapshot_validation(self):
        # Valid recording
        now = time.time()
        self.assertTrue(self.tracker.record_snapshot(oi=1000.0, price=2500.0, timestamp=now))
        self.assertEqual(len(self.tracker._history), 1)

        # Negative and zero OI rejected
        self.assertFalse(self.tracker.record_snapshot(oi=0.0, price=2500.0, timestamp=now + 1))
        self.assertFalse(self.tracker.record_snapshot(oi=-100.0, price=2500.0, timestamp=now + 2))

        # Negative and zero price rejected
        self.assertFalse(self.tracker.record_snapshot(oi=1000.0, price=0.0, timestamp=now + 3))
        self.assertFalse(self.tracker.record_snapshot(oi=1000.0, price=-5.0, timestamp=now + 4))

        # Non-numeric rejected
        self.assertFalse(self.tracker.record_snapshot(oi=float("nan"), price=2500.0, timestamp=now + 5))
        self.assertFalse(self.tracker.record_snapshot(oi=1000.0, price=float("inf"), timestamp=now + 6))

    def test_interval_delta_calculation(self):
        """
        Verify:
        OI Delta = Current OI - Previous OI
        OI Delta % = ((Current OI - Previous OI) / Previous OI) * 100
        Comparing beginning and end of interval (not just last two ticks).
        """
        t0 = 10000.0
        # t0: OI = 1000
        self.tracker.record_snapshot(oi=1000.0, price=2500.0, timestamp=t0)
        # t0 + 30s: intermediate tick
        self.tracker.record_snapshot(oi=1050.0, price=2510.0, timestamp=t0 + 30)
        # t0 + 60s (1m): OI = 1100
        self.tracker.record_snapshot(oi=1100.0, price=2520.0, timestamp=t0 + 60)

        # 1m delta: between t0 (1000) and t0+60 (1100)
        d1m = self.tracker.compute_interval_delta(60)
        self.assertEqual(d1m["current_oi"], 1100.0)
        self.assertEqual(d1m["previous_oi"], 1000.0)
        self.assertAlmostEqual(d1m["delta"], 100.0, places=4)
        self.assertAlmostEqual(d1m["delta_pct"], 10.0, places=4)

    def test_multi_interval_calculations(self):
        t0 = 10000.0
        # Fill across 1 hour: 0, 1m, 5m, 15m, 1h
        self.tracker.record_snapshot(oi=10000.0, price=2000.0, timestamp=t0)
        self.tracker.record_snapshot(oi=10100.0, price=2010.0, timestamp=t0 + 60)     # 1m mark
        self.tracker.record_snapshot(oi=10200.0, price=2020.0, timestamp=t0 + 300)    # 5m mark
        self.tracker.record_snapshot(oi=10500.0, price=2050.0, timestamp=t0 + 900)    # 15m mark
        self.tracker.record_snapshot(oi=11000.0, price=2100.0, timestamp=t0 + 3600)   # 1h mark

        all_d = self.tracker.compute_all_deltas()

        # At t0 + 3600:
        # 1h delta should compare against t0 (10000.0)
        d1h = all_d["1h"]
        self.assertEqual(d1h["current_oi"], 11000.0)
        self.assertEqual(d1h["previous_oi"], 10000.0)
        self.assertAlmostEqual(d1h["delta"], 1000.0, places=2)
        self.assertAlmostEqual(d1h["delta_pct"], 10.0, places=2)

    def test_scenario_a_breakout_oi_increase(self):
        """Scenario A: Breakout above resistance with significant OI increase."""
        t0 = time.time() - 100
        # Initial level test zone approach
        self.tracker.record_snapshot(oi=10000.0, price=2995.0, timestamp=t0)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "center_price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        # Step 1: Entering test zone
        res1 = self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=0.5)
        self.assertIn(res1["status"], ["LEVEL TESTING", "WATCHING"])

        # Step 2: Breakout with OI increasing from 10,000 to 10,500 (+5.0% > 0.5%)
        self.tracker.record_snapshot(oi=10500.0, price=3015.0, timestamp=t0 + 50)
        res2 = self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=0.5)

        self.assertEqual(res2["status"], "BREAKOUT + OI INCREASE")
        self.assertEqual(res2["scenario"], "SCENARIO_A")
        self.assertEqual(res2["badge_color"], "green")
        self.assertTrue(res2["is_breakout"])
        self.assertTrue(res2["is_new_event"])
        self.assertGreater(res2["oi_delta_pct"], 0)

    def test_scenario_b_breakout_oi_decrease(self):
        """Scenario B: Breakout below support with falling OI."""
        t0 = time.time() - 100
        self.tracker.record_snapshot(oi=10000.0, price=2002.0, timestamp=t0)

        support_level = {
            "zone_id": "sup_2000",
            "price": 2000.0,
            "center_price": 2000.0,
            "upper_price": 2005.0,
            "lower_price": 1995.0,
            "type": "support"
        }

        self.tracker.analyze_level_interaction(support_level, proximity_pct=0.35, threshold_pct=0.5)

        # Breakout down with OI dropping from 10,000 to 9,600 (-4.0% < -0.5%)
        self.tracker.record_snapshot(oi=9600.0, price=1980.0, timestamp=t0 + 40)
        res = self.tracker.analyze_level_interaction(support_level, proximity_pct=0.35, threshold_pct=0.5)

        self.assertEqual(res["status"], "BREAKOUT + OI DECREASE")
        self.assertEqual(res["scenario"], "SCENARIO_B")
        self.assertEqual(res["badge_color"], "red")
        self.assertTrue(res["is_breakout"])
        self.assertTrue(res["is_new_event"])
        self.assertLess(res["oi_delta_pct"], 0)

    def test_scenario_c_breakout_oi_neutral(self):
        """Scenario C: Breakout without significant OI change."""
        t0 = time.time() - 100
        self.tracker.record_snapshot(oi=10000.0, price=2998.0, timestamp=t0)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "center_price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=1.0)

        # Breakout price 3012.0, OI only changed by +0.1% (within [-1.0%, +1.0%])
        self.tracker.record_snapshot(oi=10010.0, price=3012.0, timestamp=t0 + 30)
        res = self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=1.0)

        self.assertEqual(res["status"], "BREAKOUT + OI NEUTRAL")
        self.assertEqual(res["scenario"], "SCENARIO_C")
        self.assertEqual(res["badge_color"], "gray")
        self.assertTrue(res["is_breakout"])
        self.assertTrue(res["is_new_event"])

    def test_scenario_d_level_test_oi_buildup(self):
        """Scenario D: Price tests level without breaking, but OI builds up rapidly."""
        t0 = time.time() - 120
        self.tracker.record_snapshot(oi=10000.0, price=3000.0, timestamp=t0)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "center_price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=0.5)

        # 45 seconds later, price is still at 3002 (inside test zone, below 3005 upper bound),
        # but OI increased by 3.5% (> 0.5 * 1.5)
        self.tracker.record_snapshot(oi=10350.0, price=3002.0, timestamp=t0 + 45)
        res = self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=0.5)

        self.assertEqual(res["status"], "LEVEL TEST + OI BUILDUP")
        self.assertEqual(res["scenario"], "SCENARIO_D")
        self.assertEqual(res["badge_color"], "amber")
        self.assertFalse(res["is_breakout"])
        self.assertTrue(res["in_test_zone"])

    # -------------------------------------------------------------
    # NEW TESTS COVERING AUDIT DEFECTS
    # -------------------------------------------------------------

    def test_adaptive_volatility_on_high_frequency_stream(self):
        """1. Verify compute_oi_volatility adapts properly on high-frequency 0.5-1.0s ticks."""
        t0 = 100000.0
        curr_oi = 50000.0

        # Simulate 15 minutes of ticks every 1.0 second with small realistic minute variations
        for sec in range(0, 960):
            if sec % 60 == 0 and sec > 0:
                # Add 0.3% to 0.6% shift every minute
                curr_oi *= 1.004
            self.tracker.record_snapshot(oi=curr_oi, price=3000.0, timestamp=t0 + sec)

        info = self.tracker.get_oi_volatility_info()
        self.assertTrue(info["is_adaptive"])
        self.assertEqual(info["status"], "OK")
        self.assertGreaterEqual(info["samples_count"], 10)
        self.assertGreaterEqual(info["threshold_pct"], 0.10)
        self.assertLessEqual(info["threshold_pct"], 2.50)

    def test_insufficient_history_for_1h(self):
        """2. Strict history requirement: 45 minutes of data must NOT be marked as OK for 1h."""
        t_now = time.time()
        t0 = t_now - 2700
        # 45 minutes = 2700s, with snapshots every 15m (0, 900, 1800, 2700)
        self.tracker.record_snapshot(oi=10000.0, price=2000.0, timestamp=t0)
        self.tracker.record_snapshot(oi=10200.0, price=2010.0, timestamp=t0 + 900)   # 15m
        self.tracker.record_snapshot(oi=10350.0, price=2030.0, timestamp=t0 + 1800)  # 30m
        self.tracker.record_snapshot(oi=10500.0, price=2050.0, timestamp=t_now)       # 45m (fresh)

        d1h = self.tracker.compute_interval_delta(3600)
        self.assertEqual(d1h["status"], "INSUFFICIENT_HISTORY")
        self.assertFalse(d1h["is_valid"])

        # But 15m (from 1800 to 2700) should be valid
        d15m = self.tracker.compute_interval_delta(900)
        self.assertEqual(d15m["status"], "OK")
        self.assertTrue(d15m["is_valid"])

    def test_data_gap_detection_10min(self):
        """3. Data gap detection: a 10-minute disconnection gap must trigger GAP_DETECTED for 1m."""
        t_now = time.time()
        t0 = t_now - 600
        self.tracker.record_snapshot(oi=10000.0, price=2000.0, timestamp=t0)
        # Big 10-minute gap (600 seconds)
        self.tracker.record_snapshot(oi=10500.0, price=2010.0, timestamp=t_now)

        # 1m delta requested at t_now
        d1m = self.tracker.compute_interval_delta(60)
        self.assertEqual(d1m["status"], "GAP_DETECTED")
        self.assertFalse(d1m["is_valid"])

        # 1m delta requested at t0 + 600
        d1m = self.tracker.compute_interval_delta(60)
        self.assertEqual(d1m["status"], "GAP_DETECTED")
        self.assertFalse(d1m["is_valid"])

    def test_impulse_breakout_pre_baseline(self):
        """4. Impulse breakout: price abruptly breaks level without earlier test state."""
        t0 = time.time() - 200
        # Price is initially at 2950 (well below resistance 3000)
        self.tracker.record_snapshot(oi=10000.0, price=2950.0, timestamp=t0)
        self.tracker.record_snapshot(oi=10100.0, price=2970.0, timestamp=t0 + 60)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "center_price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        # Price suddenly jumps to 3020 (above upper bound 3005) with OI jump to 10600
        self.tracker.record_snapshot(oi=10600.0, price=3020.0, timestamp=t0 + 90)
        res = self.tracker.analyze_level_interaction(resistance_level, proximity_pct=0.35, threshold_pct=0.5)

        self.assertTrue(res["is_breakout"])
        self.assertTrue(res["is_impulse"])
        self.assertTrue(res["is_new_event"])
        self.assertEqual(res["status"], "BREAKOUT + OI INCREASE")
        self.assertAlmostEqual(res["test_start_price"], 2970.0, places=1)
        self.assertAlmostEqual(res["test_start_oi"], 10100.0, places=1)
        self.assertGreater(res["oi_delta_pct"], 4.0)

    def test_latching_and_no_duplicate_breakout_events(self):
        """5. Latching: after initial breakout, subsequent ticks outside level do not duplicate event."""
        t0 = time.time() - 100
        self.tracker.record_snapshot(oi=10000.0, price=3000.0, timestamp=t0)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        self.tracker.analyze_level_interaction(resistance_level)

        # Tick 1: Breakout occurs
        self.tracker.record_snapshot(oi=10500.0, price=3010.0, timestamp=t0 + 10)
        res1 = self.tracker.analyze_level_interaction(resistance_level)
        self.assertTrue(res1["is_breakout"])
        self.assertTrue(res1["is_new_event"])
        self.assertEqual(res1["status"], "BREAKOUT + OI INCREASE")

        # Tick 2, 3, 4: Price remains above level
        for i in range(1, 5):
            self.tracker.record_snapshot(oi=10510.0, price=3012.0 + i, timestamp=t0 + 10 + i)
            res_sub = self.tracker.analyze_level_interaction(resistance_level)
            self.assertTrue(res_sub["is_breakout"])
            self.assertFalse(res_sub["is_new_event"])  # Latch prevents duplicate new event

    def test_breakout_reset_after_zone_return(self):
        """6. Retracement reset: returning to test zone allows a subsequent breakout event to fire."""
        t0 = time.time() - 100
        self.tracker.record_snapshot(oi=10000.0, price=3000.0, timestamp=t0)

        resistance_level = {
            "zone_id": "res_3000",
            "price": 3000.0,
            "upper_price": 3005.0,
            "lower_price": 2995.0,
            "type": "resistance"
        }

        # Breakout 1
        self.tracker.record_snapshot(oi=10500.0, price=3015.0, timestamp=t0 + 10)
        res1 = self.tracker.analyze_level_interaction(resistance_level)
        self.assertTrue(res1["is_new_event"])

        # Price returns back inside test zone (3000)
        self.tracker.record_snapshot(oi=10500.0, price=3000.0, timestamp=t0 + 20)
        res_back = self.tracker.analyze_level_interaction(resistance_level)
        self.assertFalse(res_back["is_breakout"])

        # Breakout 2 occurs with further OI expansion
        self.tracker.record_snapshot(oi=11000.0, price=3025.0, timestamp=t0 + 30)
        res2 = self.tracker.analyze_level_interaction(resistance_level)
        self.assertTrue(res2["is_breakout"])
        self.assertTrue(res2["is_new_event"])  # Clean new breakout event fired

    def test_identical_oi_checkpoint_throttling(self):
        """7. Identical OI values within 3 seconds update in place, but create checkpoints beyond 3s."""
        t0 = 500000.0
        # Tick 1
        self.tracker.record_snapshot(oi=1000.0, price=2000.0, timestamp=t0)
        self.assertEqual(len(self.tracker._history), 1)

        # 10 identical ticks within 1.0 second
        for i in range(1, 10):
            self.tracker.record_snapshot(oi=1000.0, price=2000.0, timestamp=t0 + (i * 0.1))
        # History should still have 1 entry (updated timestamp in place)
        self.assertEqual(len(self.tracker._history), 1)
        self.assertAlmostEqual(self.tracker._history[-1].timestamp, t0 + 0.9, places=3)

        # Next identical tick after 4.0 seconds -> creates checkpoint
        self.tracker.record_snapshot(oi=1000.0, price=2000.0, timestamp=t0 + 4.9)
        self.assertEqual(len(self.tracker._history), 2)

    def test_usd_notional_and_summary_fields(self):
        """8. Summary report contains both base token OI and USD notional value."""
        self.tracker.record_snapshot(oi=1000.0, price=2500.0, timestamp=time.time())
        summary = self.tracker.get_summary()

        self.assertEqual(summary["current_oi"], 1000.0)
        self.assertEqual(summary["current_oi_usd"], 2500000.0)  # 1000 * 2500
        self.assertIn("volatility_info", summary)

    def test_independent_levels_and_pairs(self):
        """9. Independent tracking for different levels and pairs in OITrackerManager."""
        mgr = OITrackerManager()
        now = time.time()
        mgr.record_tick("BTC", 40000.0, 75000.0, now)
        mgr.record_tick("ETH", 900000.0, 2200.0, now)

        btc_tracker = mgr.get_tracker("BTC")
        eth_tracker = mgr.get_tracker("ETH")

        self.assertEqual(btc_tracker.latest.oi, 40000.0)
        self.assertEqual(eth_tracker.latest.oi, 900000.0)

        # Check separate levels on BTC
        r1 = {"zone_id": "r1", "price": 76000.0, "type": "resistance"}
        r2 = {"zone_id": "r2", "price": 78000.0, "type": "resistance"}
        res1 = btc_tracker.analyze_level_interaction(r1)
        res2 = btc_tracker.analyze_level_interaction(r2)
        self.assertNotEqual(res1["level_id"], res2["level_id"])

    def test_websocket_reconnect_recovery(self):
        """10. Reconnect recovery: state freshness is maintained after silence and reconnect."""
        t0 = time.time() - 300
        # Snapshot 300s ago
        self.tracker.record_snapshot(oi=5000.0, price=100.0, timestamp=t0)
        self.assertTrue(self.tracker.is_stale)

        # Fresh tick arrives upon reconnection
        self.tracker.record_snapshot(oi=5020.0, price=101.0, timestamp=time.time())
        self.assertFalse(self.tracker.is_stale)

    def test_regression_moving_checkpoint_flaw(self):
        """Regression test 1: 60s stream of 0.5s ticks with identical OI/price creates ~20 checkpoints spanning ~60s."""
        t0 = time.time() - 70.0
        # Stream 120 ticks (every 0.5s from t0 to t0 + 59.5s)
        for i in range(120):
            ts = t0 + (i * 0.5)
            self.tracker.record_snapshot(oi=10000.0, price=2500.0, timestamp=ts)

        # There should be approximately 20 checkpoints (every 3 seconds), definitely not 1
        self.assertGreaterEqual(len(self.tracker._history), 19)
        self.assertLessEqual(len(self.tracker._history), 22)

        # Check time span (with 3s checkpoint updates, earliest snapshot is at t0+2.5, latest at t0+59.5 -> ~57s)
        span = self.tracker._history[-1].timestamp - self.tracker._history[0].timestamp
        self.assertGreaterEqual(span, 55.0)

        # compute_interval_delta for 60s should have enough data
        delta_60s = self.tracker.compute_interval_delta(60)
        self.assertEqual(delta_60s["status"], "OK")
        self.assertEqual(delta_60s["delta"], 0.0)
        self.assertEqual(delta_60s["delta_pct"], 0.0)

    def test_regression_scenario_d_buildup_latching(self):
        """Regression test 2: Scenario D generates is_new_event=True only on the first trigger, then debounces until reset."""
        t0 = time.time() - 200.0
        level = {
            "zone_id": "test_level_100",
            "price": 100.0,
            "upper_price": 100.5,
            "lower_price": 99.5,
            "type": "resistance"
        }

        # Step 1: Initial observation at 100.0 (inside test zone) with OI 10000.0
        self.tracker.record_snapshot(oi=10000.0, price=100.0, timestamp=t0)
        res0 = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertEqual(res0["status"], "LEVEL TESTING")
        self.assertFalse(res0["is_new_event"])

        # Step 2: 35 seconds later inside test zone with large OI buildup (+2.0% > 0.5 * 1.5 = 0.75%)
        self.tracker.record_snapshot(oi=10200.0, price=100.2, timestamp=t0 + 35.0)
        res1 = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertEqual(res1["status"], "LEVEL TEST + OI BUILDUP")
        self.assertEqual(res1["scenario"], "SCENARIO_D")
        self.assertTrue(res1["is_new_event"], "First buildup trigger must set is_new_event = True")

        # Step 3: Next ticks inside test zone while buildup persists: is_new_event must be False
        self.tracker.record_snapshot(oi=10220.0, price=100.3, timestamp=t0 + 36.0)
        res2 = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertEqual(res2["status"], "LEVEL TEST + OI BUILDUP")
        self.assertFalse(res2["is_new_event"], "Subsequent buildup tick must debounce is_new_event")

        self.tracker.record_snapshot(oi=10230.0, price=100.1, timestamp=t0 + 37.0)
        res3 = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertEqual(res3["status"], "LEVEL TEST + OI BUILDUP")
        self.assertFalse(res3["is_new_event"])

        # Step 4: Price leaves test zone completely (e.g. price drops to 95.0)
        self.tracker.record_snapshot(oi=10230.0, price=95.0, timestamp=t0 + 50.0)
        res_away = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertIn(res_away["status"], ["FAR", "APPROACHING"])
        self.assertFalse(self.tracker._level_states["test_level_100"].has_fired_buildup)

        # Step 5: Price returns to test zone and re-triggers buildup after another 30 seconds
        self.tracker.record_snapshot(oi=10230.0, price=100.0, timestamp=t0 + 70.0)
        self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)

        self.tracker.record_snapshot(oi=10500.0, price=100.2, timestamp=t0 + 105.0)
        res_retest = self.tracker.analyze_level_interaction(level, proximity_pct=0.5, threshold_pct=0.5)
        self.assertEqual(res_retest["status"], "LEVEL TEST + OI BUILDUP")
        self.assertTrue(res_retest["is_new_event"], "After leaving and re-entering, a new buildup should fire")

    def test_regression_zero_variance_drift_rms(self):
        """Regression test 3: Uniform 0.30% 1-minute drift produces RMS ~0.30% and threshold ~0.36% (not clamped to 0.10%)."""
        t_base = time.time() - 1500.0
        current_oi = 10000.0
        # 21 snapshots spaced 60s apart, each with a +0.30% OI increase
        for minute in range(21):
            ts = t_base + (minute * 60.0)
            self.tracker.record_snapshot(oi=current_oi, price=100.0, timestamp=ts)
            current_oi *= 1.003  # exactly +0.30%

        info = self.tracker.get_oi_volatility_info()
        self.assertTrue(info["is_adaptive"])
        self.assertEqual(info["status"], "OK")
        self.assertIn("rms_pct", info)
        self.assertAlmostEqual(info["rms_pct"], 0.30, delta=0.02)
        # Threshold should be 1.2 * RMS = 0.36% (+/- 0.02%), not minimum bound 0.10%
        self.assertAlmostEqual(info["threshold_pct"], 0.36, delta=0.03)


if __name__ == "__main__":
    unittest.main()
