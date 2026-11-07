import unittest
from app.analyzer.liquidity import detect_liquidity_and_sweeps


class TestTrendlineQuality(unittest.TestCase):
    def test_healthy_resistance_trendline_detected(self):
        """A clean, steady downtrend with spaced lower highs should detect a resistance trendline."""
        base_time = 1700000000
        candles = []
        # Pattern:
        # High at bar 3: 2500
        # Low at bar 8: 2400
        # High at bar 13: 2460 (lower high, 10 bars apart from bar 3)
        # Low at bar 18: 2360
        # Price continuing under the trendline
        prices = [
            # 0..2
            (2470, 2480, 2460, 2475),
            (2475, 2485, 2470, 2480),
            (2480, 2490, 2475, 2485),
            # 3: Peak 1
            (2485, 2500, 2480, 2490),
            # 4..7: decline
            (2485, 2488, 2450, 2455),
            (2455, 2460, 2430, 2435),
            (2435, 2440, 2410, 2415),
            (2415, 2420, 2390, 2395),
            # 8: Low 1
            (2395, 2405, 2380, 2400),
            # 9..12: bounce to Lower High
            (2400, 2420, 2395, 2415),
            (2415, 2435, 2410, 2430),
            (2430, 2450, 2425, 2445),
            (2445, 2458, 2440, 2455),
            # 13: Peak 2 (Lower High: 2460)
            (2455, 2460, 2445, 2450),
            # 14..19: drop continuing under line
            (2450, 2452, 2420, 2425),
            (2425, 2430, 2400, 2405),
            (2405, 2410, 2380, 2385),
            (2385, 2390, 2360, 2365),
            (2365, 2370, 2350, 2355),
            (2355, 2360, 2340, 2345),
        ]
        for idx, (o, h, l, c) in enumerate(prices):
            candles.append({
                "time": base_time + idx * 300,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1000.0,
            })

        res = detect_liquidity_and_sweeps(candles, interval="5m")
        trendlines = res.get("trendlines", [])
        res_tls = [tl for tl in trendlines if tl["type"] == "resistance_trendline"]
        self.assertEqual(len(res_tls), 1)
        tl = res_tls[0]
        self.assertEqual(tl["label"], "Наклонка (Опір)")
        self.assertEqual(tl["p1"]["price"], 2500.0)
        self.assertEqual(tl["p2"]["price"], 2460.0)

    def test_vertical_pump_dump_cliff_rejected(self):
        """A single vertical cliff dump (2450 -> 2200 in 1-2 bars) followed by sideways chop must NOT form a vertical trendline."""
        base_time = 1700000000
        candles = []
        # Normal chop, then massive vertical spike to 2450 and crash to 2200 in 2 bars, then horizontal chop at 2240
        prices = [
            (2250, 2260, 2245, 2255),
            (2255, 2265, 2250, 2260),
            (2260, 2270, 2255, 2265),
            (2265, 2280, 2260, 2275),
            # Giant pump spike bar
            (2275, 2450, 2270, 2440),
            # Giant dump bar right back down
            (2440, 2445, 2210, 2215),
            # Bottom chop / flat
            (2215, 2240, 2200, 2235),
            (2235, 2245, 2230, 2240),
            (2240, 2248, 2235, 2242),
            (2242, 2246, 2238, 2240),
            (2240, 2245, 2236, 2238),
            (2238, 2242, 2235, 2239),
        ]
        for idx, (o, h, l, c) in enumerate(prices):
            candles.append({
                "time": base_time + idx * 300,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 5000.0,
            })

        res = detect_liquidity_and_sweeps(candles, interval="5m")
        trendlines = res.get("trendlines", [])
        # The vertical cliff (2450 -> 2240) must be rejected because slope is excessively steep and broken by sideways candles
        res_tls = [tl for tl in trendlines if tl["type"] == "resistance_trendline" and tl["p1"]["price"] == 2450.0]
        self.assertEqual(len(res_tls), 0)

    def test_broken_trendline_invalidated_by_breakout(self):
        """If price decisively broke above a resistance trendline, it should no longer be displayed as active resistance."""
        base_time = 1700000000
        candles = []
        prices = [
            (2500, 2520, 2490, 2510),
            (2510, 2515, 2480, 2485),
            (2485, 2490, 2460, 2465),
            (2465, 2470, 2440, 2445),
            (2445, 2475, 2440, 2470),  # LH at 2475
            (2470, 2472, 2430, 2435),
            (2435, 2440, 2410, 2415),
            # Massive breakout candle breaking far above the line!
            (2415, 2550, 2410, 2540),
            (2540, 2560, 2530, 2555),
            (2555, 2570, 2550, 2565),
        ]
        for idx, (o, h, l, c) in enumerate(prices):
            candles.append({
                "time": base_time + idx * 300,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 2000.0,
            })

        res = detect_liquidity_and_sweeps(candles, interval="5m")
        trendlines = res.get("trendlines", [])
        # Active resistance should NOT include the broken line
        res_tls = [tl for tl in trendlines if tl["type"] == "resistance_trendline"]
        self.assertEqual(len(res_tls), 0)


if __name__ == "__main__":
    unittest.main()
