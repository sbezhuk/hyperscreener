import unittest
from app.analyzer.trendline import (
    find_swings_for_trendlines,
    detect_timeframe_trendlines,
    calculate_atr,
)
from app.analyzer.mtf_trendline import MTFTrendlineManager


class TestIndependentTrendlines(unittest.TestCase):
    def setUp(self):
        self.mtf_mgr = MTFTrendlineManager(cache_ttl_seconds=60.0)
        self.mtf_mgr.clear_cache()

    def _generate_downtrend_candles(self, base_time: int, interval_seconds: int, p1_price: float, p2_price: float):
        """Generates candles forming a clean descending resistance trendline."""
        # 20 bars: Peak at bar 3 (p1_price), Peak at bar 13 (p2_price < p1_price)
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
                # Valley between 3 and 13
                dist = min(i - 3, 13 - i)
                base = min(p1_price, p2_price) - 30.0 + dist * 2.0
                o, h, l, c = base, base + 4.0, base - 4.0, base
            else:
                # Continuing down under the line after bar 13
                base = p2_price + slope * (i - 13) - 8.0
                o, h, l, c = base, base + 2.0, base - 6.0, base - 3.0

            candles.append({
                "time": t,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1000.0
            })
        return candles

    def _generate_uptrend_candles(self, base_time: int, interval_seconds: int, p1_price: float, p2_price: float):
        """Generates candles forming a clean ascending support trendline."""
        # 20 bars: Valley at bar 3 (p1_price), Valley at bar 13 (p2_price > p1_price)
        candles = []
        slope = (p2_price - p1_price) / 10.0
        for i in range(20):
            t = base_time + i * interval_seconds
            if i == 3:
                l = p1_price
                h = p1_price + 10.0
                o = p1_price + 5.0
                c = p1_price + 3.0
            elif i == 13:
                l = p2_price
                h = p2_price + 10.0
                o = p2_price + 6.0
                c = p2_price + 4.0
            elif i < 3:
                base = p1_price + (3 - i) * 8.0
                o, h, l, c = base, base + 5.0, base - 5.0, base - 2.0
            elif 3 < i < 13:
                # Peak between 3 and 13
                dist = min(i - 3, 13 - i)
                base = max(p1_price, p2_price) + 30.0 - dist * 2.0
                o, h, l, c = base, base + 4.0, base - 4.0, base
            else:
                # Continuing up above the line after bar 13
                base = p2_price + slope * (i - 13) + 8.0
                o, h, l, c = base, base + 6.0, base - 2.0, base + 3.0

            candles.append({
                "time": t,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": 1000.0
            })
        return candles

    def test_1_each_timeframe_independently_determines_swings(self):
        """1. Кожен таймфрейм самостійно визначає Swing High та Swing Low."""
        base_time = 1700000000
        c_15m = self._generate_downtrend_candles(base_time, 900, 2500.0, 2450.0)
        c_1h = self._generate_uptrend_candles(base_time, 3600, 2000.0, 2100.0)

        swings_15m = find_swings_for_trendlines(c_15m, interval="15m")
        swings_1h = find_swings_for_trendlines(c_1h, interval="1h")

        # 15m swings must identify 15m peaks and valleys
        high_prices_15m = [h["price"] for h in swings_15m["highs"]]
        self.assertIn(2500.0, high_prices_15m)
        self.assertIn(2450.0, high_prices_15m)

        # 1h swings must identify 1h peaks and valleys
        low_prices_1h = [l["price"] for l in swings_1h["lows"]]
        self.assertIn(2000.0, low_prices_1h)
        self.assertIn(2100.0, low_prices_1h)

        # They must not leak into each other
        self.assertNotIn(2000.0, high_prices_15m)
        self.assertNotIn(2500.0, low_prices_1h)

    def test_2_1h_lines_not_used_for_15m(self):
        """2. Лінії 1h не використовуються для побудови ліній 15m."""
        base_time = 1700000000
        c_15m = self._generate_uptrend_candles(base_time, 900, 1800.0, 1850.0)
        c_1h = self._generate_downtrend_candles(base_time, 3600, 3200.0, 3100.0)

        tls_15m = detect_timeframe_trendlines(c_15m, interval="15m")
        tls_1h = detect_timeframe_trendlines(c_1h, interval="1h")

        self.assertTrue(len(tls_15m) > 0)
        self.assertTrue(len(tls_1h) > 0)

        # 15m must have support line around 1800 -> 1850
        sup_15m = [tl for tl in tls_15m if tl["line_type"] == "support_trendline"][0]
        self.assertEqual(sup_15m["start_point"]["price"], 1800.0)
        self.assertEqual(sup_15m["end_point"]["price"], 1850.0)
        self.assertEqual(sup_15m["timeframe"], "15m")

        # 1h must have resistance line around 3200 -> 3100
        res_1h = [tl for tl in tls_1h if tl["line_type"] == "resistance_trendline"][0]
        self.assertEqual(res_1h["start_point"]["price"], 3200.0)
        self.assertEqual(res_1h["end_point"]["price"], 3100.0)
        self.assertEqual(res_1h["timeframe"], "1h")

        # 15m lines must contain ZERO coordinates from 1h
        for tl in tls_15m:
            self.assertNotEqual(tl["start_point"]["price"], 3200.0)
            self.assertNotEqual(tl["end_point"]["price"], 3100.0)

    def test_3_4h_lines_not_used_for_1h(self):
        """3. Лінії 4h не використовуються для побудови ліній 1h."""
        base_time = 1700000000
        c_1h = self._generate_downtrend_candles(base_time, 3600, 2400.0, 2350.0)
        c_4h = self._generate_uptrend_candles(base_time, 14400, 1500.0, 1600.0)

        tls_1h = detect_timeframe_trendlines(c_1h, interval="1h")
        tls_4h = detect_timeframe_trendlines(c_4h, interval="4h")

        self.assertTrue(len(tls_1h) > 0)
        self.assertTrue(len(tls_4h) > 0)

        # 1h has resistance 2400 -> 2350
        tl_1h = tls_1h[0]
        self.assertEqual(tl_1h["timeframe"], "1h")
        self.assertEqual(tl_1h["line_type"], "resistance_trendline")
        self.assertEqual(tl_1h["start_point"]["price"], 2400.0)

        # 4h has support 1500 -> 1600
        tl_4h = tls_4h[0]
        self.assertEqual(tl_4h["timeframe"], "4h")
        self.assertEqual(tl_4h["line_type"], "support_trendline")
        self.assertEqual(tl_4h["start_point"]["price"], 1500.0)

        # Strictly independent: no coordinates shared
        self.assertNotEqual(tl_1h["start_point"]["price"], tl_4h["start_point"]["price"])

    def test_4_opposite_trend_directions_can_coexist_simultaneously(self):
        """4. На різних таймфреймах можуть одночасно існувати протилежні трендові напрямки."""
        base_time = 1700000000
        # 15m is in a local downtrend (Lower Highs -> Resistance Trendline)
        c_15m = self._generate_downtrend_candles(base_time, 900, 2500.0, 2460.0)
        # 4h is in a macro uptrend (Higher Lows -> Support Trendline)
        c_4h = self._generate_uptrend_candles(base_time, 14400, 2000.0, 2200.0)

        tls_15m = detect_timeframe_trendlines(c_15m, interval="15m")
        tls_4h = detect_timeframe_trendlines(c_4h, interval="4h")

        res_15m = [tl for tl in tls_15m if tl["line_type"] == "resistance_trendline"]
        sup_4h = [tl for tl in tls_4h if tl["line_type"] == "support_trendline"]

        self.assertEqual(len(res_15m), 1)
        self.assertEqual(res_15m[0]["direction"], "DESCENDING")

        self.assertEqual(len(sup_4h), 1)
        self.assertEqual(sup_4h[0]["direction"], "ASCENDING")

        # Opposite directions coexist cleanly
        self.assertNotEqual(res_15m[0]["direction"], sup_4h[0]["direction"])

    def test_5_timeframe_switching_does_not_transfer_alien_lines(self):
        """5. Перемикання таймфреймів не призводить до перенесення чужих ліній."""
        base_time = 1700000000
        c_15m = self._generate_downtrend_candles(base_time, 900, 2800.0, 2750.0)
        c_1h = self._generate_uptrend_candles(base_time, 3600, 2100.0, 2200.0)

        # Store 15m in cache
        tls_15m = detect_timeframe_trendlines(c_15m, interval="15m")
        self.mtf_mgr.store_cached_trendlines("ETH", "15m", tls_15m, c_15m[-1]["time"])

        # Store 1h in cache
        tls_1h = detect_timeframe_trendlines(c_1h, interval="1h")
        self.mtf_mgr.store_cached_trendlines("ETH", "1h", tls_1h, c_1h[-1]["time"])

        # Fetch 15m cached
        retrieved_15m = self.mtf_mgr.get_cached_trendlines("ETH", "15m")
        retrieved_1h = self.mtf_mgr.get_cached_trendlines("ETH", "1h")

        self.assertEqual(len(retrieved_15m), 1)
        self.assertEqual(retrieved_15m[0]["timeframe"], "15m")
        self.assertEqual(retrieved_15m[0]["start_point"]["price"], 2800.0)

        self.assertEqual(len(retrieved_1h), 1)
        self.assertEqual(retrieved_1h[0]["timeframe"], "1h")
        self.assertEqual(retrieved_1h[0]["start_point"]["price"], 2100.0)

        # Changing 15m does not affect 1h
        self.mtf_mgr.store_cached_trendlines("ETH", "15m", [], 0)
        self.assertEqual(len(self.mtf_mgr.get_cached_trendlines("ETH", "15m")), 0)
        self.assertEqual(len(self.mtf_mgr.get_cached_trendlines("ETH", "1h")), 1)

    def test_6_new_candles_update_local_timeframe_lines(self):
        """6. Нові свічки оновлюють локальні лінії відповідного таймфрейму (активна -> пробита)."""
        base_time = 1700000000
        # 1. Healthy active downtrend line
        candles = self._generate_downtrend_candles(base_time, 300, 2500.0, 2460.0)
        tls_initial = detect_timeframe_trendlines(candles, interval="5m")
        self.assertEqual(len(tls_initial), 1)
        self.assertEqual(tls_initial[0]["status"], "ACTIVE")

        # 2. Append new breakout candles far above resistance line
        last_time = candles[-1]["time"]
        for k in range(1, 4):
            candles.append({
                "time": last_time + k * 300,
                "open": 2550.0,
                "high": 2570.0,
                "low": 2540.0,
                "close": 2565.0,  # Decisive close above resistance
                "volume": 3000.0
            })

        # When include_broken=True, status is BROKEN
        tls_with_broken = detect_timeframe_trendlines(candles, interval="5m", include_broken=True)
        broken_tl = [tl for tl in tls_with_broken if tl["line_type"] == "resistance_trendline"][0]
        self.assertEqual(broken_tl["status"], "BROKEN")

        # When include_broken=False (active only), broken line is excluded
        tls_active_only = detect_timeframe_trendlines(candles, interval="5m", include_broken=False)
        self.assertEqual(len(tls_active_only), 0)

    def test_7_insufficient_significant_extremums_does_not_build_artificial_lines(self):
        """7. Відсутність достатньої кількості значущих екстремумів не призводить до побудови штучних ліній."""
        base_time = 1700000000
        # Horizontal flat chop: 20 candles oscillating tightly around 2000
        candles = []
        for i in range(20):
            candles.append({
                "time": base_time + i * 300,
                "open": 2000.0 + (i % 2) * 0.5,
                "high": 2001.0,
                "low": 1999.5,
                "close": 2000.0 + ((i + 1) % 2) * 0.5,
                "volume": 500.0
            })

        tls = detect_timeframe_trendlines(candles, interval="5m")
        # Must not fabricate artificial trendlines out of flat noise
        self.assertEqual(len(tls), 0)

    def test_8_no_duplicates_or_incorrect_lines(self):
        """8. Відсутність дублювання та некоректних ліній (вертикальні або пробиті всередині)."""
        base_time = 1700000000
        # Vertical cliff spike: 2250 -> 2450 in 1 bar, then sideways chop
        candles = [
            {"time": base_time + 0 * 300, "open": 2250.0, "high": 2260.0, "low": 2245.0, "close": 2255.0, "volume": 1000},
            {"time": base_time + 1 * 300, "open": 2255.0, "high": 2265.0, "low": 2250.0, "close": 2260.0, "volume": 1000},
            {"time": base_time + 2 * 300, "open": 2260.0, "high": 2270.0, "low": 2255.0, "close": 2265.0, "volume": 1000},
            {"time": base_time + 3 * 300, "open": 2265.0, "high": 2450.0, "low": 2260.0, "close": 2440.0, "volume": 5000},
            {"time": base_time + 4 * 300, "open": 2440.0, "high": 2445.0, "low": 2210.0, "close": 2215.0, "volume": 5000},
            {"time": base_time + 5 * 300, "open": 2215.0, "high": 2240.0, "low": 2200.0, "close": 2235.0, "volume": 1000},
            {"time": base_time + 6 * 300, "open": 2235.0, "high": 2245.0, "low": 2230.0, "close": 2240.0, "volume": 1000},
            {"time": base_time + 7 * 300, "open": 2240.0, "high": 2248.0, "low": 2235.0, "close": 2242.0, "volume": 1000},
            {"time": base_time + 8 * 300, "open": 2242.0, "high": 2246.0, "low": 2238.0, "close": 2240.0, "volume": 1000},
            {"time": base_time + 9 * 300, "open": 2240.0, "high": 2245.0, "low": 2236.0, "close": 2238.0, "volume": 1000},
        ]

        tls = detect_timeframe_trendlines(candles, interval="5m")
        # Vertical cliff from 2450 must NOT be accepted as a trendline
        invalid_tls = [tl for tl in tls if tl["start_point"]["price"] == 2450.0]
        self.assertEqual(len(invalid_tls), 0)

    def test_9_trendline_structure_contains_all_required_spec_fields(self):
        """Перевірка наявності всіх 10 обов'язкових полів з розділу 7 ТЗ."""
        base_time = 1700000000
        candles = self._generate_downtrend_candles(base_time, 900, 2500.0, 2460.0)
        tls = detect_timeframe_trendlines(candles, interval="15m")
        self.assertTrue(len(tls) > 0)
        tl = tls[0]

        # 10 Required fields per Section 7:
        self.assertIn("timeframe", tl)
        self.assertEqual(tl["timeframe"], "15m")
        self.assertIn("direction", tl)
        self.assertEqual(tl["direction"], "DESCENDING")
        self.assertIn("line_type", tl)
        self.assertEqual(tl["line_type"], "resistance_trendline")
        self.assertIn("start_point", tl)
        self.assertIn("price", tl["start_point"])
        self.assertIn("time", tl["start_point"])
        self.assertIn("end_point", tl)
        self.assertIn("price", tl["end_point"])
        self.assertIn("time", tl["end_point"])
        self.assertIn("slope", tl)
        self.assertIn("touch_count", tl)
        self.assertIn("strength", tl)
        self.assertIn("status", tl)
        self.assertIn("last_updated", tl)


if __name__ == "__main__":
    unittest.main()
