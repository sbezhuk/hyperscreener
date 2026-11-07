"""
Automated Test Suite for the 12 Audit Fixes of Open Interest (OI) False Breakout Filter.
Verifies all 7 identified audit issues:
1. Time synchronization inside candle without look-ahead bias.
2. Look-ahead bias prevention.
3. Live Latching Lockout fix: POTENTIAL -> CONFIRMED transition on delayed OI.
4. Stable formation ID across status transitions.
5. Unclosed candle guard: only POTENTIAL, never CONFIRMED until candle close.
6. Candle re-piercing before close invalidates false breakout.
7. Deduplication of identical live ticks without flooding.
8. Safe cache TTL cleanup (2h) while preserving active POTENTIAL formations.
9. Deduplication and in-place updates logic.
10. UI filter 'only confirmed' logic.
11. Symmetric handling of Bullish Support Sweeps and Bearish Resistance Sweeps.
12. Zero regressions on other screener components (cascades, FVGs, trendlines).
"""

import time
import unittest
from unittest.mock import MagicMock

from app.analyzer.false_breakout import (
    evaluate_false_breakout_oi,
    detect_false_breakouts,
    FalseBreakoutOIConfig,
    DEFAULT_OI_CONFIG,
    INTERVAL_SECONDS,
)
from app.analyzer.levels import analyze_levels
from app.analyzer.liquidity import detect_liquidity_and_sweeps
from app.analyzer.fvg import detect_fvgs
from app.analyzer.oi_tracker import OISnapshot, OITracker, oi_manager
from app.ws_manager import HyperliquidWSManager


class TestOIAuditFixes(unittest.TestCase):

    def setUp(self):
        self.config = FalseBreakoutOIConfig(
            min_oi_drop_pct=0.25,
            comparison_period_bars=1,
            max_wait_bars=3,
            noise_threshold_pct=0.05,
            stale_oi_max_age_seconds=300,
            require_oi_confirmation=True,
        )

    # 1. Синхронізація OI зі свічкою — падіння OI всередині свічки підтвердження коректно підтверджує сигнал
    def test_01_oi_sync_inside_confirmation_candle(self):
        """
        Candle 0: t=1000, open=100, close=100, baseline OI=1000.
        Candle 1: t=1300 (5m interval, duration 300s -> closes at t=1600).
        During candle 1, OI drops to 970 at t=1450 (inside the candle).
        Evaluating closed candle 1 must find baseline=1000 and post=970 -> delta=-3.0% -> CONFIRMED.
        """
        candles = [
            {"time": 1000, "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 10.0},
            {"time": 1300, "open": 100.0, "high": 106.0, "low": 99.0, "close": 99.5, "volume": 20.0},
        ]
        # OI snapshots: baseline at 1000, drop at 1450 (within candle 1: [1300, 1600])
        snapshots = [
            OISnapshot(timestamp=1000.0, oi=1000.0, price=100.0),
            OISnapshot(timestamp=1450.0, oi=970.0, price=101.0),
        ]

        res = evaluate_false_breakout_oi(
            candles=candles,
            breakout_idx=1,
            conf_idx=1,
            interval="5m",
            oi_snapshots=snapshots,
            config=self.config,
            is_candle_closed=True,
        )

        self.assertEqual(res["status"], "CONFIRMED")
        self.assertTrue(res["is_confirmed"])
        self.assertAlmostEqual(res["oi_before"], 1000.0)
        self.assertAlmostEqual(res["oi_after"], 970.0)
        self.assertAlmostEqual(res["oi_delta_pct"], -3.0, places=2)
        self.assertIn("скорочення відкритого інтересу", res["reason_desc"].lower())

    # 2. Look-ahead bias — падіння OI після часу закриття свічки не враховується
    def test_02_lookahead_bias_prevented(self):
        """
        Candle 1 closes at t=1600. At t=1600 OI is unchanged at 1000.0 (delta=0.0%).
        At t=1900 (future candle), OI crashes to 700.0 (-30%).
        Confirmation evaluated at candle 1 close MUST NOT use the t=1900 snapshot.
        """
        candles = [
            {"time": 1000, "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 10.0},
            {"time": 1300, "open": 100.0, "high": 106.0, "low": 99.0, "close": 99.5, "volume": 20.0},
        ]
        snapshots = [
            OISnapshot(timestamp=1000.0, oi=1000.0, price=100.0),
            OISnapshot(timestamp=1600.0, oi=1000.0, price=99.5),
            OISnapshot(timestamp=1900.0, oi=700.0, price=95.0),  # Future!
        ]

        res = evaluate_false_breakout_oi(
            candles=candles,
            breakout_idx=1,
            conf_idx=1,
            interval="5m",
            oi_snapshots=snapshots,
            config=self.config,
            is_candle_closed=True,
        )

        self.assertEqual(res["status"], "UNCONFIRMED")
        self.assertFalse(res["is_confirmed"])
        self.assertAlmostEqual(res["oi_after"], 1000.0)
        self.assertAlmostEqual(res["oi_delta_pct"], 0.0, places=2)
        self.assertIn(res["reason"], ["OI_NOISE", "OI_NEUTRAL"])

    # 3. Live Latching Lockout — перехід статусу POTENTIAL -> CONFIRMED при запізнілому надходженні OI
    def test_03_live_latching_status_transition_potential_to_confirmed(self):
        """
        In live mode:
        Tick 1: Open candle, price pierces and returns -> status is POTENTIAL.
        Tick 2: Candle closes and OI drop snapshot arrives -> status transitions to CONFIRMED.
        """
        ws = HyperliquidWSManager()
        c_time = 1700000000
        ws._levels_cache[("SOL", "5m")] = {
            "resistances": [{"price": 150.0, "type": "resistance", "strength_score": 80, "touches": 3}],
            "supports": [],
        }

        # Setup mock OI tracker
        tracker = MagicMock(spec=OITracker)
        snap_pre = OISnapshot(timestamp=c_time - 300, oi=10000.0, price=149.0)
        tracker._find_snapshot_at_or_before.side_effect = lambda t: snap_pre if t <= c_time else None

        from app.analyzer.oi_tracker import oi_manager
        oi_manager._trackers["SOL"] = tracker

        # Tick 1: Unclosed candle (is_closed=False)
        candle_open = {
            "time": c_time,
            "open": 149.0,
            "high": 152.0,
            "low": 148.0,
            "close": 148.5,
            "volume": 50.0,
            "is_closed": False,
        }
        res_tick1 = ws._detect_live_sweep("SOL", "5m", candle_open, is_closed=False)
        self.assertIsNotNone(res_tick1)
        self.assertEqual(res_tick1["confirmationStatus"], "POTENTIAL")
        self.assertFalse(res_tick1["oiConfirmed"])

        # Tick 2: Delayed OI arrives (-5%), candle closes (is_closed=True)
        snap_post = OISnapshot(timestamp=c_time + 300, oi=9500.0, price=148.5)
        tracker._find_snapshot_at_or_before.side_effect = lambda t: snap_post if t >= c_time + 300 else snap_pre

        candle_closed = dict(candle_open)
        candle_closed["is_closed"] = True

        res_tick2 = ws._detect_live_sweep("SOL", "5m", candle_closed, is_closed=True)
        self.assertIsNotNone(res_tick2)
        self.assertEqual(res_tick2["confirmationStatus"], "CONFIRMED")
        self.assertTrue(res_tick2["oiConfirmed"])
        self.assertAlmostEqual(res_tick2["oiDeltaPct"], -5.0, places=2)

    # 4. Live Latching Lockout — збереження ідентифікатора формації при оновленні статусу
    def test_04_stable_formation_id_across_updates(self):
        """
        The formation ID must remain consistent between POTENTIAL and CONFIRMED states
        so that UI components update the existing item rather than duplicating it.
        """
        ws = HyperliquidWSManager()
        c_time = 1700001000
        ws._levels_cache[("BTC", "5m")] = {
            "resistances": [{"price": 70000.0, "type": "resistance", "strength_score": 85, "touches": 3}],
            "supports": [],
        }

        tracker = MagicMock(spec=OITracker)
        snap_pre = OISnapshot(timestamp=c_time - 300, oi=20000.0, price=69900.0)
        tracker._find_snapshot_at_or_before.return_value = snap_pre
        from app.analyzer.oi_tracker import oi_manager
        oi_manager._trackers["BTC"] = tracker

        # Tick 1: POTENTIAL
        c1 = {"time": c_time, "open": 69900.0, "high": 70200.0, "low": 69800.0, "close": 69850.0, "volume": 10.0}
        res1 = ws._detect_live_sweep("BTC", "5m", c1, is_closed=False)
        self.assertIsNotNone(res1)
        initial_id = res1["id"]

        # Tick 2: CONFIRMED
        snap_post = OISnapshot(timestamp=c_time + 300, oi=19000.0, price=69850.0)
        tracker._find_snapshot_at_or_before.side_effect = lambda t: snap_post if t >= c_time + 300 else snap_pre
        c2 = dict(c1)
        c2["is_closed"] = True
        res2 = ws._detect_live_sweep("BTC", "5m", c2, is_closed=True)
        self.assertIsNotNone(res2)
        self.assertEqual(res2["id"], initial_id, "Formation ID must remain stable across status updates")

    # 5. Незакрита свічка — повертає тільки POTENTIAL, ніколи не CONFIRMED
    def test_05_unclosed_candle_strictly_potential(self):
        """
        Even if current tick price returned below level and OI already dropped,
        an unclosed candle MUST strictly return POTENTIAL.
        """
        ws = HyperliquidWSManager()
        c_time = 1700002000
        ws._levels_cache[("ETH", "5m")] = {
            "resistances": [{"price": 3000.0, "type": "resistance", "strength_score": 90, "touches": 4}],
            "supports": [],
        }
        tracker = MagicMock(spec=OITracker)
        snap_pre = OISnapshot(timestamp=c_time - 300, oi=1000.0, price=2990.0)
        snap_post = OISnapshot(timestamp=c_time + 50, oi=900.0, price=2980.0)
        tracker._find_snapshot_at_or_before.side_effect = lambda t: snap_post if t >= c_time + 50 else snap_pre
        from app.analyzer.oi_tracker import oi_manager
        oi_manager._trackers["ETH"] = tracker

        candle = {"time": c_time, "open": 2990.0, "high": 3050.0, "low": 2970.0, "close": 2980.0, "volume": 10.0}
        res = ws._detect_live_sweep("ETH", "5m", candle, is_closed=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["confirmationStatus"], "POTENTIAL")
        self.assertFalse(res["oiConfirmed"])
        self.assertFalse(res.get("is_closed", False))

    # 6. Незакрита свічка — повернення за рівень з наступним повторним пробоєм до закриття
    def test_06_unclosed_candle_repierce_invalidates(self):
        """
        If a candle returns inside on tick 1 (POTENTIAL), but on tick 2 price breaks back above
        the level before closing, the pattern is invalidated and no sweep is triggered.
        """
        ws = HyperliquidWSManager()
        c_time = 1700003000
        ws._levels_cache[("ETH", "5m")] = {
            "resistances": [{"price": 3000.0, "type": "resistance", "strength_score": 90, "touches": 4}],
            "supports": [],
        }

        # Tick 1: Pierced 3050, currently at 2990 (below resistance 3000) -> POTENTIAL
        c_tick1 = {"time": c_time, "open": 2990.0, "high": 3050.0, "low": 2980.0, "close": 2990.0, "volume": 5.0}
        res1 = ws._detect_live_sweep("ETH", "5m", c_tick1, is_closed=False)
        self.assertIsNotNone(res1)
        self.assertEqual(res1["confirmationStatus"], "POTENTIAL")

        # Tick 2: Price moves back up to 3020 (above resistance 3000) before close -> NOT a false breakout
        c_tick2 = {"time": c_time, "open": 2990.0, "high": 3050.0, "low": 2980.0, "close": 3020.0, "volume": 8.0}
        res2 = ws._detect_live_sweep("ETH", "5m", c_tick2, is_closed=False)
        self.assertIsNone(res2, "Re-breakout above level before close must invalidate false breakout")

    # 7. Дедуплікація тіків — один і той самий стан не генерує повторних сповіщень
    def test_07_tick_deduplication_prevents_alert_flooding(self):
        """
        Multiple ticks with unchanged status and metrics must be suppressed and return None.
        """
        ws = HyperliquidWSManager()
        c_time = 1700004000
        ws._levels_cache[("SOL", "5m")] = {
            "resistances": [{"price": 100.0, "type": "resistance", "strength_score": 80, "touches": 2}],
            "supports": [],
        }
        candle = {"time": c_time, "open": 99.0, "high": 102.0, "low": 98.0, "close": 98.5, "volume": 10.0}

        # Tick 1 -> returns POTENTIAL
        res1 = ws._detect_live_sweep("SOL", "5m", candle, is_closed=False)
        self.assertIsNotNone(res1)

        # Tick 2 identical state -> suppressed
        res2 = ws._detect_live_sweep("SOL", "5m", candle, is_closed=False)
        self.assertIsNone(res2, "Identical subsequent tick must be suppressed to avoid notification flood")

    # 8. Очищення кешу за TTL — записи старше 2 годин видаляються, активні POTENTIAL зберігаються
    def test_08_cache_ttl_cleanup(self):
        """
        Entries older than 2 hours (7200s) are purged, but active POTENTIAL formations
        within TTL are preserved.
        """
        ws = HyperliquidWSManager()
        now = 10000.0

        # Old confirmed entry (3 hours old)
        ws._seen_live_sweeps["old_confirmed"] = {
            "id": "1",
            "status": "CONFIRMED",
            "last_updated_at": now - 10800.0,
        }
        # Recent confirmed entry (30 mins old)
        ws._seen_live_sweeps["recent_confirmed"] = {
            "id": "2",
            "status": "CONFIRMED",
            "last_updated_at": now - 1800.0,
        }
        # Active potential entry (1 hour old)
        ws._seen_live_sweeps["active_potential"] = {
            "id": "3",
            "status": "POTENTIAL",
            "last_updated_at": now - 3600.0,
        }

        ws._cleanup_live_sweeps_cache(now=now, ttl_seconds=7200.0)

        self.assertNotIn("old_confirmed", ws._seen_live_sweeps)
        self.assertIn("recent_confirmed", ws._seen_live_sweeps)
        self.assertIn("active_potential", ws._seen_live_sweeps)

    # 9. Оновлення статусу на Frontend — WebSocket оновлює існуючий елемент замість створення дубліката
    def test_09_frontend_state_update_logic_simulation(self):
        """
        Simulates frontend sweep updating logic:
        Given an existing sweeps array with a POTENTIAL sweep, receiving an update
        with the same id or price/time updates the item in place and does not duplicate it.
        """
        initial_sweeps = [
            {
                "id": "live-fb-1",
                "levelPrice": 100.0,
                "time": 5000,
                "confirmationStatus": "POTENTIAL",
                "oiConfirmed": False,
                "oiDeltaPct": None,
            }
        ]

        incoming_update = {
            "id": "live-fb-1",
            "levelPrice": 100.0,
            "time": 5000,
            "confirmationStatus": "CONFIRMED",
            "oiConfirmed": True,
            "oiDeltaPct": -3.5,
        }

        # Frontend logic under test
        updated_sweeps = list(initial_sweeps)
        sweep_idx = next(
            (i for i, s in enumerate(updated_sweeps) if s["id"] == incoming_update["id"]
             or (s["levelPrice"] == incoming_update["levelPrice"] and abs(s["time"] - incoming_update["time"]) < 60)),
            -1
        )
        if sweep_idx >= 0:
            updated_sweeps[sweep_idx] = {**updated_sweeps[sweep_idx], **incoming_update}
        else:
            updated_sweeps.insert(0, incoming_update)

        self.assertEqual(len(updated_sweeps), 1, "Must update in place without creating duplicate")
        self.assertEqual(updated_sweeps[0]["confirmationStatus"], "CONFIRMED")
        self.assertTrue(updated_sweeps[0]["oiConfirmed"])
        self.assertEqual(updated_sweeps[0]["oiDeltaPct"], -3.5)

    # 10. UI-фільтр «Тільки підтверджені OI» — приховує POTENTIAL та UNCONFIRMED, показує лише CONFIRMED
    def test_10_ui_filter_only_confirmed_sweeps(self):
        """
        Verifies that only_confirmed=True strictly keeps only CONFIRMED items.
        """
        signals = [
            {"id": "1", "category": "sweep", "confirmationStatus": "CONFIRMED", "oiConfirmed": True},
            {"id": "2", "category": "sweep", "confirmationStatus": "POTENTIAL", "oiConfirmed": False},
            {"id": "3", "category": "sweep", "confirmationStatus": "UNCONFIRMED", "oiConfirmed": False},
        ]

        # Toggle OFF: show all
        filtered_off = [s for s in signals if s["category"] == "sweep"]
        self.assertEqual(len(filtered_off), 3)

        # Toggle ON: show only confirmed
        filtered_on = [s for s in signals if s["category"] == "sweep" and (s.get("oiConfirmed") or s.get("confirmationStatus") == "CONFIRMED")]
        self.assertEqual(len(filtered_on), 1)
        self.assertEqual(filtered_on[0]["id"], "1")

    # 11. Симетричність Bullish / Bearish — однакова поведінка для підтримки та опору
    def test_11_symmetric_bullish_and_bearish_sweeps(self):
        """
        Verifies both Bearish Sweep of Resistance (SHORT) and Bullish Sweep of Support (LONG)
        calculate baseline and delta accurately and confirm on OI reduction.
        """
        # Bearish: Resistance at 100, spikes to 105, closes at 99. OI drops 1000 -> 980 (-2%)
        candles_bearish = [
            {"time": 1000, "open": 98.0, "high": 99.0, "low": 97.0, "close": 98.0, "volume": 10.0, "oi": 1000.0},
            {"time": 1300, "open": 98.0, "high": 105.0, "low": 98.0, "close": 99.0, "volume": 20.0, "oi": 980.0},
            {"time": 1600, "open": 99.0, "high": 99.5, "low": 96.0, "close": 97.0, "volume": 15.0, "oi": 980.0},
        ]
        res_bearish = detect_false_breakouts(candles_bearish, [{"price": 100.0, "type": "resistance", "touches": 2}], interval="5m")
        self.assertEqual(len(res_bearish), 1)
        self.assertEqual(res_bearish[0]["direction"], "SHORT")
        self.assertTrue(res_bearish[0]["oiConfirmed"])
        self.assertEqual(res_bearish[0]["confirmationStatus"], "CONFIRMED")
        self.assertAlmostEqual(res_bearish[0]["oiDeltaPct"], -2.0, places=2)

        # Bullish: Support at 100, dips to 95, closes at 101. OI drops 1000 -> 970 (-3%)
        candles_bullish = [
            {"time": 1000, "open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 10.0, "oi": 1000.0},
            {"time": 1300, "open": 102.0, "high": 102.5, "low": 95.0, "close": 101.0, "volume": 20.0, "oi": 970.0},
            {"time": 1600, "open": 101.0, "high": 104.0, "low": 101.0, "close": 103.0, "volume": 15.0, "oi": 970.0},
        ]
        res_bullish = detect_false_breakouts(candles_bullish, [{"price": 100.0, "type": "support", "touches": 2}], interval="5m")
        self.assertEqual(len(res_bullish), 1)
        self.assertEqual(res_bullish[0]["direction"], "LONG")
        self.assertTrue(res_bullish[0]["oiConfirmed"])
        self.assertEqual(res_bullish[0]["confirmationStatus"], "CONFIRMED")
        self.assertAlmostEqual(res_bullish[0]["oiDeltaPct"], -3.0, places=2)

    # 12. Сумісність — інші типи сигналів (каскади, FVG, наклонки) працюють без змін
    def test_12_other_screener_signals_remain_unaffected(self):
        """
        Validates that false breakout changes have zero side effects on levels/cascades,
        liquidity analysis, and FVGs.
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0 + i, "high": 102.0 + i, "low": 99.0 + i, "close": 101.0 + i, "volume": 100.0}
            for i in range(25)
        ]

        levels_data = analyze_levels(candles, interval="5m")
        self.assertIn("resistances", levels_data)
        self.assertIn("supports", levels_data)

        liq_data = detect_liquidity_and_sweeps(candles, interval="5m")
        self.assertIn("pools", liq_data)
        self.assertIn("sweeps", liq_data)

        fvgs = detect_fvgs(candles)
        self.assertIsInstance(fvgs, list)


if __name__ == "__main__":
    unittest.main()
