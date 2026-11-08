import unittest
import math
from unittest.mock import AsyncMock, patch
from typing import List, Dict, Any

from app.analyzer.screener import (
    enrich_signals_with_trendline_context,
    _select_nearest_trendline,
    _get_trendline_price_at_bar,
    analyze_coin_data,
)
from app.analyzer.mtf_trendline import mtf_trendline_manager


class TestSignalStructuralContext(unittest.TestCase):
    def setUp(self):
        self.base_time = 1700000000
        mtf_trendline_manager.clear_cache()

    def _generate_candles(self, count: int = 30, base_price: float = 2000.0, step: int = 900) -> List[Dict[str, Any]]:
        """Generates regular LTF candles with realistic ATR."""
        candles = []
        for i in range(count):
            t = self.base_time + i * step
            p = base_price + i * 2.0
            candles.append({
                "time": t,
                "open": float(p - 1.0),
                "high": float(p + 5.0),
                "low": float(p - 5.0),
                "close": float(p),
                "volume": 1000.0,
            })
        return candles

    def _generate_htf_candles(self, count: int = 40, trend: str = "BULLISH", step: int = 3600) -> List[Dict[str, Any]]:
        """
        Generates synthetic HTF candles starting 35 bars in the past so >= 20 closed
        bars exist at LTF evaluation time, strictly satisfying the Point-in-Time invariant.
        """
        candles = []
        htf_start_time = self.base_time - 35 * step
        for i in range(count):
            t = htf_start_time + i * step
            drift = (i * 6.0) if trend == "BULLISH" else (-i * 6.0 if trend == "BEARISH" else 0.0)
            wave = 22.0 * math.sin(i * 2.0 * math.pi / 12.0)
            p = 2000.0 + drift + wave
            candles.append({
                "time": t,
                "open": float(p),
                "high": float(p + 3.0),
                "low": float(p - 3.0),
                "close": float(p),
                "volume": 1000.0,
            })
        return candles

    def _make_dummy_trendline(
        self,
        line_type: str = "support_trendline",
        q: float = 85.0,
        dist_atr: float = 0.2,
        comp_ratio: float = 1.0,
        status: str = "ACTIVE",
        interaction_state: str = "APPROACHING",
        p1_time: int = 1700000000,
        p2_time: int = 1700005000,
        current_price: float = 2000.0,
    ) -> Dict[str, Any]:
        """Creates a mock trendline structure for enrichment tests."""
        return {
            "id": f"tl-15m-{line_type}-{p1_time}",
            "type": line_type,
            "line_type": line_type,
            "status": status,
            "interaction_state": interaction_state,
            "structural_quality": q,
            "strength": q,
            "compression_ratio": comp_ratio,
            "distance_to_line_atr": dist_atr,
            "start_point": {"time": p1_time, "price": current_price, "index": 5},
            "end_point": {"time": p2_time, "price": current_price, "index": 15},
            "slope": 0.0,
        }

    # 1. LONG Sweep + Support Confluence
    def test_long_sweep_support_confluence(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        support_tl = self._make_dummy_trendline("support_trendline", q=88.0, current_price=curr_price)

        signals = [{
            "id": "sweep-1",
            "category": "sweep",
            "direction": "LONG",
            "price": curr_price,
            "time": candles[-1]["time"],
            "title": "Bullish Sweep",
        }]

        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[support_tl],
            candles=candles,
            interval="15m",
        )

        ctx = enriched[0]["structuralContext"]
        self.assertTrue(ctx["contextAvailable"])
        self.assertTrue(ctx["hasSupportConfluence"])
        self.assertEqual(ctx["confluentLineQ"], 88.0)
        self.assertEqual(ctx["structuralTier"], "TIER_1_CONFLUENT")

    # 2. LONG FVG + Support Confluence
    def test_long_fvg_support_confluence(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        support_tl = self._make_dummy_trendline("support_trendline", q=82.5, current_price=curr_price)

        signals = [{
            "id": "fvg-1",
            "category": "fvg",
            "direction": "LONG",
            "price": curr_price,
            "time": candles[-1]["time"],
            "title": "Bullish FVG Test",
        }]

        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[support_tl],
            candles=candles,
            interval="15m",
        )

        ctx = enriched[0]["structuralContext"]
        self.assertTrue(ctx["contextAvailable"])
        self.assertTrue(ctx["hasSupportConfluence"])
        self.assertEqual(ctx["confluentLineQ"], 82.5)
        self.assertEqual(ctx["structuralTier"], "TIER_1_CONFLUENT")

    # 3. Absence of Confluence (dist > 0.50 ATR or Q < 80)
    def test_absence_of_confluence(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]

        # Case A: Q < 80 (e.g. 75.0)
        support_low_q = self._make_dummy_trendline("support_trendline", q=75.0, current_price=curr_price)
        signals_a = [{"id": "s-1", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched_a = enrich_signals_with_trendline_context(signals=signals_a, active_trendlines=[support_low_q], candles=candles, interval="15m")
        self.assertFalse(enriched_a[0]["structuralContext"]["hasSupportConfluence"])
        self.assertEqual(enriched_a[0]["structuralContext"]["structuralTier"], "TIER_2_STANDARD")

        # Case B: Far distance (line at 2200 while price at 2000 -> dist > 0.50 ATR)
        support_far = self._make_dummy_trendline("support_trendline", q=90.0, current_price=2200.0)
        signals_b = [{"id": "s-2", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched_b = enrich_signals_with_trendline_context(signals=signals_b, active_trendlines=[support_far], candles=candles, interval="15m")
        self.assertFalse(enriched_b[0]["structuralContext"]["hasSupportConfluence"])
        self.assertGreater(enriched_b[0]["structuralContext"]["distanceToSupportAtr"], 0.50)
        self.assertEqual(enriched_b[0]["structuralContext"]["structuralTier"], "TIER_2_STANDARD")

    # 4. AGAINST_HTF
    def test_against_htf_warning(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        htf_bearish = self._generate_htf_candles(40, trend="BEARISH")

        signals = [{"id": "sweep-long", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=candles,
            interval="15m",
            htf_candles=htf_bearish,
        )

        ctx = enriched[0]["structuralContext"]
        self.assertEqual(ctx["htfAlignment"], "AGAINST_HTF")
        self.assertIn("AGAINST_HTF", ctx["riskFlags"])
        self.assertEqual(ctx["structuralTier"], "TIER_3_WARNING")

    # 5. COMPRESSION Warning
    def test_compression_warning(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        comp_tl = self._make_dummy_trendline("support_trendline", q=85.0, comp_ratio=0.55, current_price=curr_price)

        signals = [{"id": "fvg-1", "category": "fvg", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[comp_tl],
            candles=candles,
            interval="15m",
        )

        ctx = enriched[0]["structuralContext"]
        self.assertTrue(ctx["isCompression"])
        self.assertIn("COMPRESSION", ctx["riskFlags"])
        self.assertEqual(ctx["structuralTier"], "TIER_3_WARNING")

    # 6. Simultaneous AGAINST_HTF + COMPRESSION
    def test_simultaneous_against_htf_and_compression(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        htf_bearish = self._generate_htf_candles(40, trend="BEARISH")
        comp_tl = self._make_dummy_trendline("support_trendline", q=85.0, comp_ratio=0.50, current_price=curr_price)

        signals = [{"id": "sweep-1", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[comp_tl],
            candles=candles,
            interval="15m",
            htf_candles=htf_bearish,
        )

        ctx = enriched[0]["structuralContext"]
        self.assertIn("AGAINST_HTF", ctx["riskFlags"])
        self.assertIn("COMPRESSION", ctx["riskFlags"])
        self.assertEqual(ctx["structuralTier"], "TIER_3_WARNING")

    # 7. Absence of HTF data (fallback)
    def test_missing_htf_data_fallback(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]

        # Call with no HTF candles
        signals = [{"id": "sweep-1", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=candles,
            interval="15m",
            htf_candles=[],
        )

        ctx = enriched[0]["structuralContext"]
        self.assertTrue(ctx["contextAvailable"])
        self.assertEqual(ctx["htfAlignment"], "UNAVAILABLE")
        self.assertNotIn("AGAINST_HTF", ctx["riskFlags"])
        self.assertEqual(ctx["structuralTier"], "TIER_2_STANDARD")

        # Call with insufficient LTF candles (< 5)
        short_candles = candles[:3]
        enriched_short = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=short_candles,
            interval="15m",
        )
        ctx_short = enriched_short[0]["structuralContext"]
        self.assertFalse(ctx_short["contextAvailable"])
        self.assertEqual(ctx_short["unavailableReason"], "INSUFFICIENT_CANDLES")
        self.assertEqual(ctx_short["structuralTier"], "TIER_2_STANDARD")

    # 8. Deterministic line selection
    def test_deterministic_line_selection(self):
        target_price = 2000.0
        curr_bar_idx = 20
        atr = 10.0

        # Line 1: distance 5.0 (0.5 ATR), Q = 80, time = 100
        line1 = {"id": "tl1", "structural_quality": 80.0, "slope": 0.0, "start_point": {"index": 0, "price": 1995.0}, "end_point": {"time": 100, "price": 1995.0}}
        # Line 2: distance 2.0 (0.2 ATR), Q = 75, time = 200 (Closer!)
        line2 = {"id": "tl2", "structural_quality": 75.0, "slope": 0.0, "start_point": {"index": 0, "price": 1998.0}, "end_point": {"time": 200, "price": 1998.0}}
        # Line 3: distance 2.0 (0.2 ATR), Q = 90, time = 150 (Equal distance to line 2, but higher Q!)
        line3 = {"id": "tl3", "structural_quality": 90.0, "slope": 0.0, "start_point": {"index": 0, "price": 2002.0}, "end_point": {"time": 150, "price": 2002.0}}
        # Line 4: distance 2.0 (0.2 ATR), Q = 90, time = 300 (Equal dist and Q to line 3, but newer P2!)
        line4 = {"id": "tl4", "structural_quality": 90.0, "slope": 0.0, "start_point": {"index": 0, "price": 2002.0}, "end_point": {"time": 300, "price": 2002.0}}

        lines = [line1, line2, line3, line4]
        best_tl, best_dist = _select_nearest_trendline(lines, target_price, curr_bar_idx, atr)
        self.assertIsNotNone(best_tl)
        # tl4 should win because dist is 0.2 ATR, Q is 90, and P2 time 300 is newest
        self.assertEqual(best_tl["id"], "tl4")
        self.assertEqual(best_dist, 0.2)

    # 9. Absence of extra exchange requests (Zero network calls)
    @patch("app.hyperliquid.hl_client.get_candles")
    def test_zero_extra_exchange_requests(self, mock_get_candles):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        signals = [{"id": "s-1", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles[-1]["time"]}]

        # Pre-seed cache in manager
        mtf_trendline_manager.store_cached_trendlines("ETH", "15m", [])
        mtf_trendline_manager._candle_cache[("ETH", "1h")] = {"candles": self._generate_htf_candles(30), "timestamp": 9999999999}

        enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=candles,
            interval="15m",
            coin="ETH",
        )

        # Ensure get_candles was NEVER called by the enrichment function
        mock_get_candles.assert_not_called()

    # 10. Backward compatibility
    def test_backward_compatibility(self):
        candles = self._generate_candles(30, base_price=2000.0)
        curr_price = candles[-1]["close"]
        signals = [{
            "id": "original-id-123",
            "coin": "ETH",
            "interval": "15m",
            "category": "sweep",
            "title": "Bullish Sweep",
            "direction": "LONG",
            "desc": "Test Description",
            "price": curr_price,
            "distPct": 0.45,
            "time": candles[-1]["time"],
            "oiConfirmed": True,
            "confirmationStatus": "CONFIRMED",
        }]

        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=candles,
            interval="15m",
        )

        sig = enriched[0]
        # Verify original fields are unmodified
        self.assertEqual(sig["id"], "original-id-123")
        self.assertEqual(sig["coin"], "ETH")
        self.assertEqual(sig["category"], "sweep")
        self.assertEqual(sig["direction"], "LONG")
        self.assertEqual(sig["oiConfirmed"], True)
        self.assertEqual(sig["confirmationStatus"], "CONFIRMED")
        self.assertEqual(sig["distPct"], 0.45)

        # Verify both camelCase and snake_case references exist
        self.assertIn("structuralContext", sig)
        self.assertIn("structural_context", sig)
        self.assertEqual(sig["structuralContext"]["structuralTier"], sig["structural_context"]["structural_tier"])

    # 11. Strict Point-in-Time invariant
    def test_strict_pit_invariant(self):
        candles = self._generate_candles(30, base_price=2000.0, step=900)
        curr_c = candles[-1]
        eval_time = curr_c["time"] + 900  # Candle closes at time + 900

        # Create HTF candles: candle 0 closes at base_time + 3600 <= eval_time -> included
        # Candle 1 closes at base_time + 7200 > eval_time -> excluded!
        htf_candles = [
            {"time": self.base_time, "open": 2000.0, "high": 2010.0, "low": 1990.0, "close": 2005.0, "volume": 100, "close_time": self.base_time + 3600},
            {"time": self.base_time + 3600, "open": 2005.0, "high": 2050.0, "low": 2000.0, "close": 2045.0, "volume": 100, "close_time": self.base_time + 7200},
        ]

        signals = [{"id": "s-1", "category": "sweep", "direction": "LONG", "price": curr_c["close"], "time": curr_c["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[],
            candles=candles,
            interval="15m",
            htf_candles=htf_candles,
        )

        ctx = enriched[0]["structuralContext"]
        # Since < 20 closed HTF bars exist in this restricted dataset, PIT safely marks UNAVAILABLE without looking ahead
        self.assertEqual(ctx["htfAlignment"], "UNAVAILABLE")

    # 12. Timeframe isolation
    def test_timeframe_isolation(self):
        candles_15m = self._generate_candles(30, base_price=2000.0, step=900)
        curr_price = candles_15m[-1]["close"]

        tl_15m = self._make_dummy_trendline("support_trendline", q=85.0, current_price=curr_price)
        tl_15m["timeframe"] = "15m"

        signals = [{"id": "s-15m", "category": "sweep", "direction": "LONG", "price": curr_price, "time": candles_15m[-1]["time"]}]
        enriched = enrich_signals_with_trendline_context(
            signals=signals,
            active_trendlines=[tl_15m],
            candles=candles_15m,
            interval="15m",
        )

        ctx = enriched[0]["structuralContext"]
        self.assertTrue(ctx["hasSupportConfluence"])
        self.assertEqual(ctx["structuralTier"], "TIER_1_CONFLUENT")


if __name__ == "__main__":
    unittest.main()
