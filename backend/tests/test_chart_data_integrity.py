import unittest
import uuid
from app.analyzer.levels import analyze_levels, _add_legacy_fields
from app.ws_manager import HyperliquidWSManager


class TestChartDataIntegrity(unittest.IsolatedAsyncioTestCase):

    def test_level_calculation_small_12_candles(self):
        """Test levels calculation on very small candle history (e.g. newly listed coin with 12 candles like XTEN)."""
        candles = [
            {"time": 1700000000 + i * 86400, "open": 10.0 + i, "high": 11.0 + i, "low": 9.5 + i, "close": 10.5 + i, "volume": 5000.0}
            for i in range(12)
        ]
        result = analyze_levels(candles, interval="1d")
        self.assertIn("resistances", result)
        self.assertIn("supports", result)
        self.assertIn("currentPrice", result)
        self.assertEqual(result["currentPrice"], 10.5 + 11)
        for lvl in result["resistances"] + result["supports"]:
            self.assertIsInstance(lvl["firstTime"], int)
            self.assertIsInstance(lvl["latestTime"], int)
            self.assertGreater(lvl["firstTime"], 0)
            self.assertGreater(lvl["latestTime"], 0)

    def test_level_calculation_medium_61_candles(self):
        """Test levels calculation on medium candle history (e.g. USELESS with 61 candles)."""
        candles = [
            {
                "time": 1700000000 + i * 86400,
                "open": 20.0 + (1.0 if i % 2 == 0 else -1.0),
                "high": 22.0,
                "low": 18.0,
                "close": 20.0,
                "volume": 1000.0,
            }
            for i in range(61)
        ]
        result = analyze_levels(candles, interval="1d")
        self.assertIn("resistances", result)
        self.assertIn("supports", result)
        for lvl in result["resistances"] + result["supports"]:
            self.assertIsInstance(lvl["price"], float)
            self.assertIsInstance(lvl["touches"], int)

    def test_dynamic_discovery_support_atl(self):
        """Test dynamic discovery when price breaks down to all-time-low (no support with 2+ touches)."""
        # Price strictly descending: candle low reaches down to 50
        candles = [
            {"time": 1700000000 + i * 300, "open": 100.0 - i * 3, "high": 101.0 - i * 3, "low": 98.0 - i * 3, "close": 98.5 - i * 3, "volume": 100.0}
            for i in range(20)
        ]
        # Current price is at the lowest candle
        res = analyze_levels(candles, interval="5m")
        # Ensure analyze_levels completes without KeyError: 'first_detected_at'
        self.assertIsInstance(res["supports"], list)
        for s in res["supports"]:
            self.assertIn("firstTime", s)
            self.assertIn("latestTime", s)
            self.assertIn("first_detected_at", s)
            self.assertIn("last_tested_at", s)

    def test_dynamic_discovery_resistance_ath(self):
        """Test dynamic discovery when price breaks out to all-time-high (no resistance with 2+ touches)."""
        candles = [
            {"time": 1700000000 + i * 300, "open": 50.0 + i * 3, "high": 53.0 + i * 3, "low": 49.0 + i * 3, "close": 52.5 + i * 3, "volume": 100.0}
            for i in range(20)
        ]
        res = analyze_levels(candles, interval="5m")
        self.assertIsInstance(res["resistances"], list)
        for r in res["resistances"]:
            self.assertIn("firstTime", r)
            self.assertIn("latestTime", r)
            self.assertIn("first_detected_at", r)
            self.assertIn("last_tested_at", r)

    def test_legacy_fields_graceful_defaults(self):
        """Ensure _add_legacy_fields never raises KeyError if first_detected_at or last_tested_at is absent."""
        zone = {
            "center_price": 100.0,
            "upper_price": 102.0,
            "lower_price": 98.0,
            "touches_count": 1,
            "strength_score": 70.0,
        }
        res = _add_legacy_fields(zone, current_price=101.0)
        self.assertEqual(res["firstTime"], 0)
        self.assertEqual(res["latestTime"], 0)
        self.assertEqual(res["price"], 100.0)
        self.assertEqual(res["touches"], 1)

    async def test_ws_topic_subscription_lifecycle(self):
        """Verify that switching topics unsubscribes old topic and does not create duplicate subscriptions."""
        mgr = HyperliquidWSManager()
        # Mock client
        class DummyWS:
            async def send_text(self, text):
                pass
        client = DummyWS()
        await mgr.register_client(client)

        # Subscribe to ETH 1d
        await mgr.subscribe_client(client, "ETH", "1d")
        self.assertIn(("ETH", "1d"), mgr._subscribed_topics)
        self.assertIn(("ETH", "1d"), mgr._client_subs[client])

        # Switch: unsubscribe ETH 1d, subscribe BTC 1d
        await mgr.unsubscribe_client(client, "ETH", "1d")
        self.assertNotIn(("ETH", "1d"), mgr._subscribed_topics)
        self.assertNotIn(("ETH", "1d"), mgr._client_subs[client])

        await mgr.subscribe_client(client, "BTC", "1d")
        self.assertIn(("BTC", "1d"), mgr._subscribed_topics)
        self.assertIn(("BTC", "1d"), mgr._client_subs[client])

        # Subscribe again to the same topic -> verify NO duplicates
        await mgr.subscribe_client(client, "BTC", "1d")
        self.assertEqual(len([t for t in mgr._subscribed_topics if t == ("BTC", "1d")]), 1)

        # Cleanup
        await mgr.unregister_client(client)
        self.assertNotIn(("BTC", "1d"), mgr._subscribed_topics)


if __name__ == "__main__":
    unittest.main()
