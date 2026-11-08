import unittest
from app.analyzer.levels import analyze_levels, _calculate_atr


class TestSupportPierceIntegrity(unittest.TestCase):
    """
    Tests ensuring that support and resistance levels do NOT disappear
    when price pierces or sweeps through them (preventing false breakout bugs).
    """

    def test_demand_ob_persists_during_support_pierce(self):
        """
        Critical bug test: When price pierces below a confirmed Demand Order Block
        (false breakout / sweep), the support level must remain intact on the chart
        and not disappear or jump lower.
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 100}
            for i in range(20)
        ]
        # Bullish setup candle establishing Demand OB at [98.5 .. 100.5] (center 99.5)
        candles.append({"time": 7000, "open": 100.0, "high": 100.5, "low": 98.5, "close": 98.7, "volume": 200})
        candles.append({"time": 7300, "open": 99.0, "high": 105.0, "low": 98.8, "close": 104.5, "volume": 500})
        candles.append({"time": 7600, "open": 104.5, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 300})

        # 1. Price is at 105.0 (above support)
        res_before = analyze_levels(candles, interval="5m")
        sup_before = next((s for s in res_before["supports"] if s["smc_label"] == "OB Demand"), None)
        self.assertIsNotNone(sup_before)
        self.assertEqual(sup_before["price"], 99.5)

        # 2. Price pierces below support: candle wicks down to 98.0 and closes at 99.0
        pierced_candles = list(candles)
        pierced_candles.append({"time": 7900, "open": 104.0, "high": 104.0, "low": 98.0, "close": 99.0, "volume": 400})

        res_pierced = analyze_levels(pierced_candles, interval="5m")
        self.assertEqual(res_pierced["currentPrice"], 99.0)

        # The Demand OB at 99.5 MUST NOT disappear!
        sup_pierced = next((s for s in res_pierced["supports"] if s["price"] == 99.5), None)
        self.assertIsNotNone(
            sup_pierced,
            "Critical bug: Support level at 99.5 disappeared when price pierced down to 99.0!"
        )
        self.assertEqual(sup_pierced["smc_label"], "OB Demand")
        self.assertTrue(sup_pierced.get("swept_liquidity"))
        self.assertTrue(sup_pierced.get("is_pierced"))

        # 3. Price bounces back to 101.5 (reclaim after false breakout)
        reclaimed_candles = list(pierced_candles)
        reclaimed_candles.append({"time": 8200, "open": 99.0, "high": 102.0, "low": 98.8, "close": 101.5, "volume": 450})

        res_reclaimed = analyze_levels(reclaimed_candles, interval="5m")
        sup_reclaimed = next((s for s in res_reclaimed["supports"] if s["price"] == 99.5), None)
        self.assertIsNotNone(sup_reclaimed, "Support level disappeared after false breakout reclaim!")

    def test_ssl_pool_persists_during_sweep(self):
        """
        Sell-side liquidity (SSL) Equal Lows must persist as support when swept,
        allowing false breakout detection to trigger.
        """
        candles = []
        t = 1000
        for i in range(25):
            candles.append({"time": t, "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.1, "volume": 100})
            t += 300

        # Low 1 at 99.0
        candles.append({"time": t, "open": 100.1, "high": 100.3, "low": 99.0, "close": 99.8, "volume": 150}); t += 300
        for i in range(4):
            candles.append({"time": t, "open": 99.8, "high": 100.5, "low": 99.6, "close": 100.2, "volume": 200}); t += 300

        # Low 2 at 99.05
        candles.append({"time": t, "open": 100.2, "high": 100.4, "low": 99.05, "close": 99.9, "volume": 180}); t += 300
        for i in range(4):
            candles.append({"time": t, "open": 99.9, "high": 100.6, "low": 99.7, "close": 100.3, "volume": 250}); t += 300

        # Sweep
        candles.append({"time": t, "open": 100.3, "high": 100.3, "low": 98.6, "close": 99.2, "volume": 350}); t += 300

        res = analyze_levels(candles, interval="5m")
        # Support around 99.0 must exist and be retained
        sup = next((s for s in res["supports"] if abs(s["price"] - 99.0) <= 0.6), None)
        self.assertIsNotNone(sup, "SSL pool disappeared when swept!")

    def test_supply_ob_persists_during_resistance_pierce(self):
        """
        Bearish Supply OB must persist as resistance when price pierces above it (bull trap / false breakout).
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0, "volume": 100}
            for i in range(20)
        ]
        # Bullish setup candle establishing Supply OB at [99.5 .. 102.0]
        candles.append({"time": 7000, "open": 99.0, "high": 102.0, "low": 98.8, "close": 101.8, "volume": 200})
        candles.append({"time": 7300, "open": 101.5, "high": 101.8, "low": 95.0, "close": 95.5, "volume": 500})
        candles.append({"time": 7600, "open": 95.5, "high": 96.0, "low": 92.0, "close": 93.0, "volume": 300})

        # Price pumps and pierces above 102.0: high 102.8, close 102.2
        pierced_candles = list(candles)
        pierced_candles.append({"time": 7900, "open": 93.0, "high": 102.8, "low": 93.0, "close": 102.2, "volume": 400})

        res_pierced = analyze_levels(pierced_candles, interval="5m")
        res_ob = next((r for r in res_pierced["resistances"] if abs(r["price"] - 100.75) <= 0.5), None)
        self.assertIsNotNone(res_ob, "Supply OB disappeared when price pierced above it!")

    def test_support_flips_to_resistance_after_sustained_breakdown(self):
        """
        Role Reversal: If price breaks through support and does NOT return back (sustained breakdown),
        the support level flips to overhead resistance (Підтримка -> Опір, Breaker).
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 102.0, "low": 99.5, "close": 100.5, "volume": 100}
            for i in range(20)
        ]
        # Support formed at 99.5
        candles.append({"time": 7000, "open": 100.0, "high": 100.5, "low": 98.5, "close": 98.7, "volume": 200})
        candles.append({"time": 7300, "open": 99.0, "high": 105.0, "low": 98.8, "close": 104.5, "volume": 500})
        candles.append({"time": 7600, "open": 104.5, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 300})

        # Sustained breakdown: price collapses to 94.0 and stays below
        candles.append({"time": 7900, "open": 103.0, "high": 103.0, "low": 95.0, "close": 95.5, "volume": 800})
        candles.append({"time": 8200, "open": 95.5, "high": 96.0, "low": 91.0, "close": 92.0, "volume": 600})
        candles.append({"time": 8500, "open": 92.0, "high": 95.0, "low": 91.5, "close": 94.0, "volume": 400})

        res = analyze_levels(candles, interval="5m")
        self.assertEqual(res["currentPrice"], 94.0)

        # The level around 99.5 - 101.0 must now be in RESISTANCES (flipped to resistance)
        flipped_res = next((r for r in res["resistances"] if r["price"] > 94.0 and r.get("smc_type") == "BREAKER_BLOCK"), None)
        self.assertIsNotNone(
            flipped_res,
            "Broken support did not flip to resistance (Role Reversal failed)!"
        )
        self.assertEqual(flipped_res["type"], "resistance")
        self.assertEqual(flipped_res["smc_label"], "Breaker")

    def test_resistance_flips_to_support_after_sustained_breakout(self):
        """
        Role Reversal: If price breaks through resistance and does NOT return back (sustained breakout),
        the resistance level flips to underlying support (Опір -> Підтримка, Breaker).
        """
        candles = [
            {"time": 1000 + i * 300, "open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0, "volume": 100}
            for i in range(20)
        ]
        # Resistance formed at [99.5 .. 102.0]
        candles.append({"time": 7000, "open": 99.0, "high": 102.0, "low": 98.8, "close": 101.8, "volume": 200})
        candles.append({"time": 7300, "open": 101.5, "high": 101.8, "low": 95.0, "close": 95.5, "volume": 500})
        candles.append({"time": 7600, "open": 95.5, "high": 96.0, "low": 92.0, "close": 93.0, "volume": 300})

        # Sustained breakout: price pumps to 108.0 and stays above
        candles.append({"time": 7900, "open": 93.0, "high": 104.0, "low": 93.0, "close": 103.5, "volume": 700})
        candles.append({"time": 8200, "open": 103.5, "high": 108.0, "low": 103.0, "close": 107.5, "volume": 600})
        candles.append({"time": 8500, "open": 107.5, "high": 109.0, "low": 106.0, "close": 107.0, "volume": 400})

        res = analyze_levels(candles, interval="5m")
        self.assertEqual(res["currentPrice"], 107.0)

        # The broken resistance must now be in SUPPORTS (flipped to support)
        flipped_sup = next((s for s in res["supports"] if s["price"] < 107.0 and s.get("smc_type") == "BREAKER_BLOCK"), None)
        self.assertIsNotNone(
            flipped_sup,
            "Broken resistance did not flip to support (Role Reversal failed)!"
        )
        self.assertEqual(flipped_sup["type"], "support")
        self.assertEqual(flipped_sup["smc_label"], "Breaker")


if __name__ == "__main__":
    unittest.main()
