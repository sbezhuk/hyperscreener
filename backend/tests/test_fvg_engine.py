import unittest
import time
from app.analyzer.fvg import calculate_atr, detect_and_track_fvgs, compute_mtf_confluences

class TestFVGEngine(unittest.TestCase):
    def setUp(self):
        self.base_time = 1700000000

    def create_candle(self, offset_i, o, h, l, c, v=100.0):
        return {
            "time": self.base_time + offset_i * 300,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v)
        }

    def test_bullish_fvg_detection(self):
        """Test classic 3-candle Bullish FVG where C3.low > C1.high"""
        candles = [
            self.create_candle(0, 100, 105, 99, 104),   # C1: High = 105
            self.create_candle(1, 104, 120, 103, 118),  # C2: Impulse candle (large green body)
            self.create_candle(2, 118, 122, 110, 121),  # C3: Low = 110 > C1.high(105)
        ]
        fvgs = detect_and_track_fvgs(candles, interval="5m", symbol="ETH")
        self.assertEqual(len(fvgs), 1)
        f = fvgs[0]
        self.assertEqual(f["type"], "BULLISH")
        self.assertEqual(f["lower_price"], 105.0)
        self.assertEqual(f["upper_price"], 110.0)
        self.assertEqual(f["midpoint_price"], 107.5) # CE
        self.assertEqual(f["mitigation_status"], "FRESH")
        self.assertEqual(f["mitigation_percent"], 0.0)
        self.assertFalse(f["ce_reached"])
        self.assertGreaterEqual(f["strength_score"], 40)

    def test_bearish_fvg_detection(self):
        """Test classic 3-candle Bearish FVG where C3.high < C1.low"""
        candles = [
            self.create_candle(0, 120, 122, 115, 116),  # C1: Low = 115
            self.create_candle(1, 116, 117, 98, 100),   # C2: Impulse red candle
            self.create_candle(2, 100, 108, 97, 101),   # C3: High = 108 < C1.low(115)
        ]
        fvgs = detect_and_track_fvgs(candles, interval="15m", symbol="BTC")
        self.assertEqual(len(fvgs), 1)
        f = fvgs[0]
        self.assertEqual(f["type"], "BEARISH")
        self.assertEqual(f["lower_price"], 108.0)
        self.assertEqual(f["upper_price"], 115.0)
        self.assertEqual(f["midpoint_price"], 111.5) # CE
        self.assertEqual(f["mitigation_status"], "FRESH")

    def test_partial_and_50_percent_mitigation(self):
        """Test mitigation tracking: entering zone, reaching CE (50%)"""
        candles = [
            self.create_candle(0, 100, 105, 99, 104),   # C1: High = 105
            self.create_candle(1, 104, 125, 104, 124),  # C2: Impulse
            self.create_candle(2, 124, 128, 115, 127),  # C3: Low = 115 (gap 105 to 115, CE=110)
            # C4 tests zone down to 112 (enters zone [105, 115], penetration = 115-112 = 3 out of 10 => 30%)
            self.create_candle(3, 127, 127, 112, 114),
        ]
        fvgs = detect_and_track_fvgs(candles, interval="5m")
        self.assertEqual(len(fvgs), 1)
        f = fvgs[0]
        self.assertEqual(f["mitigation_status"], "PARTIALLY MITIGATED")
        self.assertEqual(f["mitigation_percent"], 30.0)
        self.assertFalse(f["ce_reached"])

        # Add C5 reaching 109 (penetrates past CE 110)
        candles.append(self.create_candle(4, 114, 116, 109, 111))
        fvgs2 = detect_and_track_fvgs(candles, interval="5m")
        f2 = fvgs2[0]
        self.assertEqual(f2["mitigation_status"], "50% MITIGATED")
        self.assertTrue(f2["ce_reached"])
        self.assertEqual(f2["ce_first_time"], candles[4]["time"])
        self.assertEqual(f2["ce_close_after"], 111.0)

    def test_fully_mitigated(self):
        """Test 100% full mitigation through the entire gap without candle close inversion"""
        candles = [
            self.create_candle(0, 100, 105, 99, 104),
            self.create_candle(1, 104, 125, 104, 124),
            self.create_candle(2, 124, 128, 115, 127), # Bullish FVG [105, 115]
            # C4 pierces down to 104 with wick but closes at 106 (above lower bound 105)
            self.create_candle(3, 127, 127, 104, 106),
        ]
        fvgs = detect_and_track_fvgs(candles, interval="5m")
        self.assertEqual(len(fvgs), 1)
        f = fvgs[0]
        self.assertEqual(f["mitigation_percent"], 100.0)
        self.assertEqual(f["mitigation_status"], "FULLY MITIGATED")

    def test_inverse_fvg_inversion(self):
        """Test Bullish FVG turning into Bearish IFVG upon confirmed close below lower bound"""
        candles = [
            self.create_candle(0, 100, 105, 99, 104),
            self.create_candle(1, 104, 125, 104, 124),
            self.create_candle(2, 124, 128, 115, 127), # Bullish FVG [105, 115]
            # C4 closes below lower bound 105 (e.g. close=102)
            self.create_candle(3, 120, 120, 101, 102),
        ]
        fvgs = detect_and_track_fvgs(candles, interval="5m")
        self.assertEqual(len(fvgs), 1)
        f = fvgs[0]
        self.assertEqual(f["mitigation_status"], "INVERTED")
        self.assertEqual(f["inversion_status"], "CONFIRMED")
        self.assertEqual(f["ifvg_type"], "BEARISH_IFVG")
        self.assertEqual(f["inversion_price"], 102.0)

    def test_multi_timeframe_independence_and_confluence(self):
        """Test that different timeframes retain independent zones and calculate confluence overlap"""
        # 15m FVG: 99500 to 99600
        fvg_15m = {
            "fvg_id": "fvg_eth_15m_1",
            "timeframe": "15m",
            "type": "BULLISH",
            "lower_price": 99500.0,
            "upper_price": 99600.0,
            "midpoint_price": 99550.0,
            "mitigation_status": "FRESH",
            "strength_score": 85
        }
        # 1h FVG: 99480 to 99620
        fvg_1h = {
            "fvg_id": "fvg_eth_1h_1",
            "timeframe": "1h",
            "type": "BULLISH",
            "lower_price": 99480.0,
            "upper_price": 99620.0,
            "midpoint_price": 99550.0,
            "mitigation_status": "FRESH",
            "strength_score": 90
        }
        # 4h FVG: 99520 to 99700
        fvg_4h = {
            "fvg_id": "fvg_eth_4h_1",
            "timeframe": "4h",
            "type": "BULLISH",
            "lower_price": 99520.0,
            "upper_price": 99700.0,
            "midpoint_price": 99610.0,
            "mitigation_status": "50% MITIGATED",
            "strength_score": 78
        }

        all_tf = {
            "15m": [fvg_15m],
            "1h": [fvg_1h],
            "4h": [fvg_4h]
        }

        confluences = compute_mtf_confluences(all_tf, min_overlapping_tfs=2)
        self.assertGreaterEqual(len(confluences), 1)
        conf = confluences[0]
        # Overlap across all 3: max(99500, 99480, 99520) = 99520, min(99600, 99620, 99700) = 99600
        self.assertEqual(conf["lower_price"], 99520.0)
        self.assertEqual(conf["upper_price"], 99600.0)
        self.assertEqual(conf["timeframe_count"], 3)
        self.assertGreaterEqual(conf["confluence_score"], 60)

if __name__ == "__main__":
    unittest.main()
