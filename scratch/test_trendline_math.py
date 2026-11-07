import unittest
import math

def calculate_symmetric_forward_metrics(candles, t, line, horizon, atr_t, buffer_factor=0.25, clean_mfe_mult=1.5, clean_mae_mult=0.5):
    """
    Computes symmetric MFE, MAE, Breakout, and Clean Bounce relative to the dynamic Line_{t+f}.
    
    Coordinate System:
    ATR_t is fixed at contact bar t.
    All distance measurements for bar t+f are evaluated relative to Line_{t+f}.
    
    Resistance:
      f_line = Line_{t+f}
      favorable_excursion = f_line - candle['low']   (downward drop below the line)
      adverse_excursion   = candle['high'] - f_line  (upward surge above the line)
      confirmed_breakout  = candle['close'] > f_line + buffer_factor * atr_t
      wick_breach         = candle['high'] > f_line + buffer_factor * atr_t
      
    Support:
      f_line = Line_{t+f}
      favorable_excursion = candle['high'] - f_line  (upward bounce above the line)
      adverse_excursion   = f_line - candle['low']   (downward drop below the line)
      confirmed_breakout  = candle['close'] < f_line - buffer_factor * atr_t
      wick_breach         = candle['low'] < f_line - buffer_factor * atr_t
    """
    idx1 = line["p1"]["index"]
    p1_price = line["p1"]["price"]
    slope = line["slope"]
    is_res = (line["type"] == "resistance_trendline")
    
    max_mfe = 0.0
    max_mae = 0.0
    confirmed_breakout = False
    wick_only_breach = False
    first_breakout_bar = None
    
    # Track sequence of threshold crossings for conservative ambiguity resolution
    mfe_threshold = clean_mfe_mult * atr_t
    mae_threshold = clean_mae_mult * atr_t
    
    mfe_hit_bar = None
    mae_hit_bar = None
    
    for f in range(1, horizon + 1):
        if t + f >= len(candles):
            break
        c = candles[t + f]
        f_line = p1_price + slope * (t + f - idx1)
        
        if is_res:
            fav = f_line - c["low"]
            adv = c["high"] - f_line
            is_break_close = c["close"] > f_line + buffer_factor * atr_t
            is_break_wick = c["high"] > f_line + buffer_factor * atr_t
        else:
            fav = c["high"] - f_line
            adv = f_line - c["low"]
            is_break_close = c["close"] < f_line - buffer_factor * atr_t
            is_break_wick = c["low"] < f_line - buffer_factor * atr_t
            
        if fav > max_mfe:
            max_mfe = fav
        if adv > max_mae:
            max_mae = adv
            
        if is_break_close and not confirmed_breakout:
            confirmed_breakout = True
            if first_breakout_bar is None:
                first_breakout_bar = f
        elif is_break_wick and not confirmed_breakout:
            wick_only_breach = True
            
        # Check threshold hits
        if fav >= mfe_threshold and mfe_hit_bar is None:
            mfe_hit_bar = f
        if adv > mae_threshold and mae_hit_bar is None:
            mae_hit_bar = f
            
    mfe_atr = max(0.0, max_mfe) / atr_t
    mae_atr = max(0.0, max_mae) / atr_t
    
    # Resolve intra-bar / sequence ambiguity:
    # If both MFE >= 1.5 and MAE > 0.5 occurred:
    # If MAE was hit on an earlier bar than MFE -> Stop-out occurred before profit target.
    # If hit on the same bar -> Conservative assumption: adverse excursion (MAE) hit first.
    if mae_hit_bar is not None and mfe_hit_bar is not None:
        if mae_hit_bar <= mfe_hit_bar:
            clean_bounce = False
        else:
            clean_bounce = True
    elif mfe_hit_bar is not None and mae_hit_bar is None:
        clean_bounce = True
    else:
        clean_bounce = False
        
    return {
        "mfe_atr": round(mfe_atr, 4),
        "mae_atr": round(mae_atr, 4),
        "confirmed_breakout": confirmed_breakout,
        "wick_only_breach": wick_only_breach and not confirmed_breakout,
        "clean_bounce": clean_bounce,
        "first_breakout_bar": first_breakout_bar,
        "mfe_hit_bar": mfe_hit_bar,
        "mae_hit_bar": mae_hit_bar,
    }


class TestTrendlineMathSymmetry(unittest.TestCase):
    """
    Unit tests ensuring symmetric MFE / MAE computation relative to Line_{t+f}
    and verification across various geometric scenarios.
    """

    def setUp(self):
        self.atr = 10.0
        self.horizon = 5

    def test_horizontal_line(self):
        """
        Scenario 1: Horizontal Line (slope = 0)
        Line is at price 100.0.
        For slope=0, Line_{t+f} == Line_t.
        Verify that dynamic formulas give exact same values as static formula.
        """
        line = {
            "type": "resistance_trendline",
            "p1": {"price": 100.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": 0.0,
        }
        # Contact at t=10.
        candles = [None] * 10 + [
            {"time": 10, "open": 98.0, "high": 100.0, "low": 97.0, "close": 98.0}, # t=10 (touch)
            {"time": 11, "open": 98.0, "high": 99.0, "low": 85.0, "close": 86.0},   # low=85 (drop 15 = 1.5 ATR)
            {"time": 12, "open": 86.0, "high": 88.0, "low": 84.0, "close": 85.0},   # low=84 (drop 16 = 1.6 ATR)
            {"time": 13, "open": 85.0, "high": 87.0, "low": 83.0, "close": 84.0},   # low=83 (drop 17 = 1.7 ATR)
            {"time": 14, "open": 84.0, "high": 85.0, "low": 82.0, "close": 83.0},   # low=82 (drop 18 = 1.8 ATR)
            {"time": 15, "open": 83.0, "high": 84.0, "low": 80.0, "close": 81.0},   # low=80 (drop 20 = 2.0 ATR)
        ]
        res = calculate_symmetric_forward_metrics(candles, t=10, line=line, horizon=5, atr_t=self.atr)
        # Expected:
        # Max drop below 100 is 100 - 80 = 20.0 -> MFE = 2.0 ATR
        # Max high above 100 is 0.0 (high never exceeded 100) -> MAE = 0.0 ATR
        # Clean bounce: MFE >= 1.5, MAE <= 0.5 -> True
        # Breakout: False
        self.assertEqual(res["mfe_atr"], 2.0)
        self.assertEqual(res["mae_atr"], 0.0)
        self.assertTrue(res["clean_bounce"])
        self.assertFalse(res["confirmed_breakout"])

    def test_ascending_support_clean_bounce(self):
        """
        Scenario 2: Ascending Support (slope = +2.0 $/bar)
        At t=10: Line_10 = 100.0.
        At t+1: Line_11 = 102.0. Candle high = 118.0, low = 102.0. Favorable = 118 - 102 = 16.0 (1.6 ATR).
        Verify that dynamic line elevation is properly subtracted from high.
        """
        line = {
            "type": "support_trendline",
            "p1": {"price": 80.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": 2.0,
        }
        candles = [None] * 10 + [
            {"time": 10, "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0}, # t=10 (touch at 100)
            {"time": 11, "open": 102.0, "high": 118.0, "low": 102.0, "close": 117.0}, # Line_11 = 102.0
            {"time": 12, "open": 117.0, "high": 122.0, "low": 105.0, "close": 120.0}, # Line_12 = 104.0 (fav = 122-104=18)
            {"time": 13, "open": 120.0, "high": 125.0, "low": 110.0, "close": 124.0}, # Line_13 = 106.0 (fav = 125-106=19)
            {"time": 14, "open": 124.0, "high": 127.0, "low": 115.0, "close": 126.0}, # Line_14 = 108.0 (fav = 127-108=19)
            {"time": 15, "open": 126.0, "high": 130.0, "low": 120.0, "close": 128.0}, # Line_15 = 110.0 (fav = 130-110=20)
        ]
        res = calculate_symmetric_forward_metrics(candles, t=10, line=line, horizon=5, atr_t=self.atr)
        # Dynamic MFE: max(High - Line_{t+f}) = 130 - 110 = 20.0 -> 2.0 ATR.
        # Static formula would have wrongly calculated: 130 - 100 = 30.0 (3.0 ATR)!
        # Dynamic MAE: min(Low - Line_{t+f}) -> all lows >= line, so MAE = 0.0.
        self.assertEqual(res["mfe_atr"], 2.0)
        self.assertEqual(res["mae_atr"], 0.0)
        self.assertTrue(res["clean_bounce"])
        self.assertFalse(res["confirmed_breakout"])

    def test_descending_resistance_clean_bounce(self):
        """
        Scenario 3: Descending Resistance (slope = -2.0 $/bar)
        At t=10: Line_10 = 100.0.
        At t+5: Line_15 = 90.0.
        Candle 15: low = 70.0.
        Dynamic favorable drop: Line_15 - low = 90.0 - 70.0 = 20.0 (2.0 ATR).
        Static formula would have calculated: Line_10 - 70.0 = 30.0 (3.0 ATR, overestimation)!
        """
        line = {
            "type": "resistance_trendline",
            "p1": {"price": 120.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": -2.0,
        }
        candles = [None] * 10 + [
            {"time": 10, "open": 99.0, "high": 100.0, "low": 98.0, "close": 98.5},  # t=10
            {"time": 11, "open": 98.0, "high": 97.0, "low": 85.0, "close": 86.0},   # Line_11 = 98. fav = 98-85=13
            {"time": 12, "open": 86.0, "high": 90.0, "low": 80.0, "close": 82.0},   # Line_12 = 96. fav = 96-80=16
            {"time": 13, "open": 82.0, "high": 85.0, "low": 76.0, "close": 78.0},   # Line_13 = 94. fav = 94-76=18
            {"time": 14, "open": 78.0, "high": 80.0, "low": 72.0, "close": 74.0},   # Line_14 = 92. fav = 92-72=20
            {"time": 15, "open": 74.0, "high": 75.0, "low": 70.0, "close": 71.0},   # Line_15 = 90. fav = 90-70=20
        ]
        res = calculate_symmetric_forward_metrics(candles, t=10, line=line, horizon=5, atr_t=self.atr)
        self.assertEqual(res["mfe_atr"], 2.0)
        self.assertEqual(res["mae_atr"], 0.0)
        self.assertTrue(res["clean_bounce"])
        self.assertFalse(res["confirmed_breakout"])

    def test_steep_slope_line_movement_impact(self):
        """
        Scenario 4: Steep Slope Case Where Line Movement Decides Outcome.
        Resistance slope = -5.0 $/bar (0.5 ATR per bar).
        Over 5 bars, line drops by 25.0 (2.5 ATR)!
        Suppose price stays flat at 98.0:
        At t=10: Line_10 = 100. Price is 98 (2 below line).
        At t=5 (bar 15): Line_15 = 75.0. Price is still 98!
        Relative to static entry (100): Price never broke 100.
        Relative to dynamic Line (75): Price at 98 is 23 points ABOVE the descending line -> BREAKOUT!
        """
        line = {
            "type": "resistance_trendline",
            "p1": {"price": 150.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": -5.0,
        }
        candles = [None] * 10 + [
            {"time": 10, "open": 98.0, "high": 100.0, "low": 97.0, "close": 98.0}, # Line=100
            {"time": 11, "open": 98.0, "high": 98.5, "low": 97.5, "close": 98.0},  # Line=95 (above line by 3)
            {"time": 12, "open": 98.0, "high": 98.5, "low": 97.5, "close": 98.0},  # Line=90 (above line by 8)
            {"time": 13, "open": 98.0, "high": 98.5, "low": 97.5, "close": 98.0},  # Line=85 (above line by 13)
            {"time": 14, "open": 98.0, "high": 98.5, "low": 97.5, "close": 98.0},  # Line=80 (above line by 18)
            {"time": 15, "open": 98.0, "high": 98.5, "low": 97.5, "close": 98.0},  # Line=75 (above line by 23)
        ]
        res = calculate_symmetric_forward_metrics(candles, t=10, line=line, horizon=5, atr_t=self.atr)
        
        # Max adverse excursion relative to dynamic Line_15: 98.5 - 75.0 = 23.5 -> 2.35 ATR
        self.assertEqual(res["mae_atr"], 2.35)
        # Confirmed breakout is True because Close (98) > Line (95, 90, 85, etc.) + 0.25*ATR (2.5)
        self.assertTrue(res["confirmed_breakout"])
        self.assertEqual(res["first_breakout_bar"], 1) # Broke on bar 11: Close 98 > 95 + 2.5 = 97.5
        self.assertFalse(res["clean_bounce"])

    def test_breakout_confirmed_vs_wick_pierce(self):
        """
        Scenario 5: Confirmed Breakout vs Wick-Only Pierce.
        Buffer is 0.25 * ATR = 2.5 points.
        Case A: High pierces Line + 4.0, but Close returns to Line - 1.0 (Wick-only breach).
        Case B: High reaches Line + 4.0, and Close settles at Line + 3.0 (Confirmed breakout).
        """
        line = {
            "type": "resistance_trendline",
            "p1": {"price": 100.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": 0.0,
        }
        # Case A: Wick pierce only
        candles_wick = [None] * 10 + [
            {"time": 10, "open": 98.0, "high": 100.0, "low": 98.0, "close": 99.0},
            {"time": 11, "open": 99.0, "high": 104.0, "low": 97.0, "close": 98.0}, # Wick to 104 (> 102.5), Close at 98
            {"time": 12, "open": 98.0, "high": 99.0, "low": 95.0, "close": 96.0},
            {"time": 13, "open": 96.0, "high": 97.0, "low": 94.0, "close": 95.0},
            {"time": 14, "open": 95.0, "high": 96.0, "low": 93.0, "close": 94.0},
            {"time": 15, "open": 94.0, "high": 95.0, "low": 92.0, "close": 93.0},
        ]
        res_a = calculate_symmetric_forward_metrics(candles_wick, t=10, line=line, horizon=5, atr_t=self.atr)
        self.assertFalse(res_a["confirmed_breakout"])
        self.assertTrue(res_a["wick_only_breach"])
        self.assertEqual(res_a["mae_atr"], 0.4) # 104 - 100 = 4.0 -> 0.4 ATR

        # Case B: Confirmed Close Breakout
        candles_close = [None] * 10 + [
            {"time": 10, "open": 98.0, "high": 100.0, "low": 98.0, "close": 99.0},
            {"time": 11, "open": 99.0, "high": 104.0, "low": 98.0, "close": 103.0}, # Close at 103 (> 100 + 2.5)
            {"time": 12, "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0},
            {"time": 13, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0},
            {"time": 14, "open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0},
            {"time": 15, "open": 106.0, "high": 108.0, "low": 105.0, "close": 107.0},
        ]
        res_b = calculate_symmetric_forward_metrics(candles_close, t=10, line=line, horizon=5, atr_t=self.atr)
        self.assertTrue(res_b["confirmed_breakout"])
        self.assertFalse(res_b["wick_only_breach"])

    def test_dual_extreme_and_non_exclusivity(self):
        """
        Scenario 6: Dual Extremes & Non-Exclusivity.
        Single bar with extreme volatility: High goes to 108.0 (MAE = 0.8 ATR > 0.5),
        and Low goes to 80.0 (MFE = 2.0 ATR >= 1.5).
        Under conservative assumption (adverse excursion happens first),
        clean_bounce must be FALSE because stop was hit.
        """
        line = {
            "type": "resistance_trendline",
            "p1": {"price": 100.0, "index": 0},
            "p2": {"price": 100.0, "index": 10},
            "slope": 0.0,
        }
        candles = [None] * 10 + [
            {"time": 10, "open": 98.0, "high": 100.0, "low": 98.0, "close": 99.0},
            # Massive single bar candle
            {"time": 11, "open": 99.0, "high": 108.0, "low": 80.0, "close": 82.0},
            {"time": 12, "open": 82.0, "high": 84.0, "low": 81.0, "close": 83.0},
            {"time": 13, "open": 83.0, "high": 85.0, "low": 82.0, "close": 84.0},
            {"time": 14, "open": 84.0, "high": 85.0, "low": 82.0, "close": 83.0},
            {"time": 15, "open": 83.0, "high": 84.0, "low": 81.0, "close": 82.0},
        ]
        res = calculate_symmetric_forward_metrics(candles, t=10, line=line, horizon=5, atr_t=self.atr)
        self.assertEqual(res["mfe_atr"], 2.0)
        self.assertEqual(res["mae_atr"], 0.8)
        # Both thresholds were reached on bar 1 (f=1). Under conservative ordering, clean_bounce is False.
        self.assertFalse(res["clean_bounce"])

if __name__ == "__main__":
    unittest.main()
