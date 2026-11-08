import unittest
from app.analyzer.levels import (
    analyze_levels,
    _detect_smc_order_blocks,
    _detect_smc_liquidity_pools,
    _calculate_atr,
)


class TestSMCLevels(unittest.TestCase):
    """
    Tests for Smart Money Concepts (SMC) Support and Resistance Level Detection:
    - Order Blocks (Bullish OB / Bearish OB)
    - Breaker Blocks (Role Reversal)
    - Buy-side & Sell-side Liquidity Pools (BSL / SSL)
    """

    def test_bullish_order_block_detection(self):
        """
        Tests that a bearish candle followed by strong upward displacement
        creates a Bullish Order Block (Demand).
        """
        # Baseline candles
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2, "volume": 100.0}
            for i in range(5)
        ]
        # Bearish Order Block setup candle at index 5:
        # Bearish candle: Open 100.0, High 100.5, Low 98.0, Close 98.2
        candles.append({"time": 2500, "open": 100.0, "high": 100.5, "low": 98.0, "close": 98.2, "volume": 150.0})
        # Followed by strong bullish displacement in next candles:
        candles.append({"time": 2800, "open": 98.5, "high": 104.0, "low": 98.2, "close": 103.5, "volume": 500.0})
        candles.append({"time": 3100, "open": 103.5, "high": 108.0, "low": 103.0, "close": 107.5, "volume": 600.0})
        candles.append({"time": 3400, "open": 107.5, "high": 109.0, "low": 106.5, "close": 108.0, "volume": 300.0})

        atr = _calculate_atr(candles)
        obs = _detect_smc_order_blocks(candles, atr=atr, current_price=108.0, interval="5m")

        bullish_obs = [ob for ob in obs if ob["smc_label"] == "OB Demand"]
        self.assertGreater(len(bullish_obs), 0)
        dem_ob = next((ob for ob in bullish_obs if ob["first_detected_at"] == 2500), None)
        self.assertIsNotNone(dem_ob)
        self.assertEqual(dem_ob["type"], "support")
        self.assertEqual(dem_ob["smc_type"], "ORDER_BLOCK")
        self.assertEqual(dem_ob["upper_price"], 100.5)
        self.assertEqual(dem_ob["lower_price"], 98.0)
        self.assertGreaterEqual(dem_ob["strength_score"], 85.0)

    def test_bearish_order_block_detection(self):
        """
        Tests that a bullish candle followed by strong downward displacement
        creates a Bearish Order Block (Supply).
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2, "volume": 100.0}
            for i in range(5)
        ]
        # Bullish setup candle at index 5:
        candles.append({"time": 2500, "open": 100.0, "high": 102.0, "low": 99.8, "close": 101.8, "volume": 150.0})
        # Followed by strong downward displacement:
        candles.append({"time": 2800, "open": 101.5, "high": 101.8, "low": 95.0, "close": 95.5, "volume": 500.0})
        candles.append({"time": 3100, "open": 95.5, "high": 96.0, "low": 91.0, "close": 91.5, "volume": 600.0})
        candles.append({"time": 3400, "open": 91.5, "high": 92.0, "low": 89.0, "close": 90.0, "volume": 300.0})

        atr = _calculate_atr(candles)
        obs = _detect_smc_order_blocks(candles, atr=atr, current_price=90.0, interval="5m")

        bearish_obs = [ob for ob in obs if ob["smc_label"] == "OB Supply"]
        self.assertGreater(len(bearish_obs), 0)
        sup_ob = next((ob for ob in bearish_obs if ob["first_detected_at"] == 2500), None)
        self.assertIsNotNone(sup_ob)
        self.assertEqual(sup_ob["type"], "resistance")
        self.assertEqual(sup_ob["smc_type"], "ORDER_BLOCK")
        self.assertEqual(sup_ob["upper_price"], 102.0)
        self.assertEqual(sup_ob["lower_price"], 99.8)

    def test_breaker_block_role_reversal(self):
        """
        Tests that when price violates a Bullish Order Block by closing below it,
        it flips to a Bearish Breaker Block (Resistance).
        """
        candles = [
            {"time": 1000, "open": 100.0, "high": 100.5, "low": 98.0, "close": 98.2, "volume": 100.0},
            {"time": 1300, "open": 98.5, "high": 105.0, "low": 98.2, "close": 104.5, "volume": 500.0},
            {"time": 1600, "open": 104.5, "high": 106.0, "low": 103.0, "close": 105.5, "volume": 300.0},
            # Price collapses and closes below 98.0:
            {"time": 1900, "open": 104.0, "high": 104.0, "low": 94.0, "close": 95.0, "volume": 700.0},
            {"time": 2200, "open": 95.0, "high": 96.0, "low": 93.0, "close": 94.0, "volume": 200.0},
        ]
        atr = _calculate_atr(candles)
        obs = _detect_smc_order_blocks(candles, atr=atr, current_price=94.0, interval="5m")

        breakers = [ob for ob in obs if ob.get("smc_type") == "BREAKER_BLOCK"]
        self.assertGreater(len(breakers), 0)
        breaker = breakers[0]
        self.assertEqual(breaker["smc_label"], "Breaker")
        # Since current price is 94.0 (< ob center 99.25), it acts as overhead resistance!
        self.assertEqual(breaker["type"], "resistance")
        self.assertEqual(breaker["status"], "retested")

    def test_smc_analyze_levels_output(self):
        """
        Validates that analyze_levels produces SMC structures (resistances, supports, smc_summary).
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0 + (i % 4), "high": 103.0 + (i % 4), "low": 98.0 + (i % 4), "close": 101.0 + (i % 4), "volume": 100.0}
            for i in range(40)
        ]
        res = analyze_levels(candles, interval="5m")
        self.assertIn("resistances", res)
        self.assertIn("supports", res)
        self.assertIn("smc_summary", res)

        for lvl in res["resistances"] + res["supports"]:
            self.assertIn("smc_label", lvl)
            self.assertIn("price", lvl)
            self.assertIn("top", lvl)
            self.assertIn("bottom", lvl)
            self.assertIn("touches", lvl)

    def test_smc_dealing_range_strict_separation_no_overlap(self):
        """
        Validates that resistances are strictly above current price,
        supports are strictly below current price, and that resistance
        and support can NEVER collide or occupy the same price level.
        """
        candles = []
        t = 1000
        for i in range(15):
            candles.append({"time": t, "open": 2220 + (i % 5), "high": 2230 + (i % 4), "low": 2215 + (i % 3), "close": 2225 + (i % 4), "volume": 100})
            t += 14400

        candles.append({"time": t, "open": 2225, "high": 2235, "low": 2210, "close": 2232, "volume": 300}); t += 14400
        candles.append({"time": t, "open": 2232, "high": 2260, "low": 2230, "close": 2258, "volume": 800}); t += 14400
        candles.append({"time": t, "open": 2258, "high": 2285, "low": 2255, "close": 2280, "volume": 900}); t += 14400
        candles.append({"time": t, "open": 2280, "high": 2298, "low": 2275, "close": 2292, "volume": 1200}); t += 14400
        candles.append({"time": t, "open": 2292, "high": 2296, "low": 2282, "close": 2285, "volume": 1000}); t += 14400
        candles.append({"time": t, "open": 2285, "high": 2288, "low": 2240, "close": 2242, "volume": 1500}); t += 14400
        candles.append({"time": t, "open": 2242, "high": 2245, "low": 2218, "close": 2222, "volume": 1100}); t += 14400

        for i in range(12):
            candles.append({"time": t, "open": 2222 + (i % 4), "high": 2235 + (i % 3), "low": 2215 + (i % 3), "close": 2226, "volume": 150})
            t += 14400

        res = analyze_levels(candles, interval="4h")
        current_price = res["currentPrice"]

        self.assertGreater(len(res["resistances"]), 0)
        self.assertGreater(len(res["supports"]), 0)

        # 1. Strict resistance separation: bottom >= current_price
        for r in res["resistances"]:
            self.assertEqual(r["type"], "resistance")
            self.assertGreater(r["price"], current_price)
            self.assertGreaterEqual(r["bottom"], current_price)
            self.assertIn(r.get("smc_label"), ("OB Supply", "BSL", "Breaker", "Supply"))

        # 2. Strict support separation: top <= current_price
        for s in res["supports"]:
            self.assertEqual(s["type"], "support")
            self.assertLess(s["price"], current_price)
            self.assertLessEqual(s["top"], current_price)
            self.assertIn(s.get("smc_label"), ("OB Demand", "SSL", "Breaker", "Demand"))

        # 3. Non-collision invariant
        lowest_resistance = res["resistances"][0]
        highest_support = res["supports"][0]
        self.assertGreater(
            lowest_resistance["bottom"],
            highest_support["top"],
            "Resistance and Support cannot overlap or share the same price level"
        )


if __name__ == "__main__":
    unittest.main()
