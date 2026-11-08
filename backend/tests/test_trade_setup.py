import unittest
from app.analyzer.trade_setup import generate_trade_setup, _calculate_atr


class TestTradeSetup(unittest.TestCase):
    def setUp(self):
        # Generate 50 simulated candles around price 100
        self.candles = []
        base_price = 100.0
        for i in range(50):
            self.candles.append({
                "time": 1000 + i * 300,
                "open": base_price + (i * 0.1),
                "high": base_price + (i * 0.1) + 1.5,
                "low": base_price + (i * 0.1) - 1.0,
                "close": base_price + (i * 0.1) + 0.5,
                "volume": 1000.0,
            })

    def test_calculate_atr(self):
        atr = _calculate_atr(self.candles, 14)
        self.assertGreater(atr, 0.0)

    def test_valid_long_setup_with_rr_above_3(self):
        """When support is at 98, Entry at 100, SL at 97.5 (Risk = 2.5), and strong Resistance at 110 (Reward = 10), RR = 4.0 >= 3.0."""
        current_price = 100.0
        levels = {
            "supports": [
                {
                    "price": 98.0,
                    "top": 98.5,
                    "bottom": 97.8,
                    "touches": 3,
                    "strength_score": 85.0,
                    "smc_type": "ORDER_BLOCK",
                    "smc_label": "OB DEMAND",
                }
            ],
            "resistances": [
                {
                    "price": 110.0,
                    "top": 110.5,
                    "bottom": 109.8,
                    "touches": 2,
                    "strength_score": 75.0,
                    "smc_type": "ORDER_BLOCK",
                    "smc_label": "OB SUPPLY",
                }
            ],
            "pivot_points": {"pp": 100.0, "r1": 110.0, "s1": 95.0},
        }
        fvgs = [
            {
                "type": "BULLISH",
                "lower_price": 98.2,
                "upper_price": 99.5,
                "mitigation_status": "FRESH",
                "mitigation_percent": 10,
            }
        ]
        trendlines = []
        liquidity = {
            "sweeps": [
                {
                    "direction": "LONG",
                    "levelPrice": 97.9,
                    "desc": "Свіп локального мінімуму",
                    "oiConfirmed": True,
                }
            ]
        }
        structure = {"trend": "BULLISH", "summary": "Висхідний тренд"}
        oi_summary = {
            "oi_status": "INCREASING",
            "deltas": {"5m": {"delta_pct": 0.45}},
        }

        setup = generate_trade_setup(
            coin="ETH",
            interval="5m",
            current_price=current_price,
            candles=self.candles,
            levels=levels,
            fvgs=fvgs,
            trendlines=trendlines,
            liquidity=liquidity,
            structure=structure,
            oi_summary=oi_summary,
            min_rr_threshold=3.0,
        )

        self.assertEqual(setup["action"], "LOOK_FOR_LONG")
        self.assertEqual(setup["direction"], "LONG")
        self.assertIsNotNone(setup["entry_price"])
        self.assertIsNotNone(setup["entry_range"])
        self.assertIsNotNone(setup["stop_loss"])
        self.assertIsNotNone(setup["take_profit"])
        self.assertGreaterEqual(setup["risk_reward"], 3.0)
        self.assertGreater(setup["confluence_score"], 60)
        self.assertIn("ЛОНГ", setup["summary_comment"])

    def test_rejection_when_rr_below_3(self):
        """When resistance is too close (at 102), Reward = 2, Risk = 2.5 => RR = 0.8 < 3.0, setup must be REJECTED with WAIT action."""
        current_price = 100.0
        levels = {
            "supports": [
                {
                    "price": 98.0,
                    "top": 98.5,
                    "bottom": 97.8,
                    "touches": 3,
                    "strength_score": 80.0,
                }
            ],
            "resistances": [
                {
                    "price": 102.0,
                    "top": 102.5,
                    "bottom": 101.8,
                    "touches": 2,
                    "strength_score": 75.0,
                }
            ],
            "pivot_points": {},
        }
        fvgs = []
        trendlines = []
        liquidity = {"sweeps": []}
        structure = {"trend": "BULLISH"}

        setup = generate_trade_setup(
            coin="ETH",
            interval="5m",
            current_price=current_price,
            candles=self.candles,
            levels=levels,
            fvgs=fvgs,
            trendlines=trendlines,
            liquidity=liquidity,
            structure=structure,
            min_rr_threshold=3.0,
        )

        self.assertEqual(setup["action"], "WAIT")
        self.assertEqual(setup["direction"], "NEUTRAL")
        self.assertIsNone(setup["entry_price"])
        self.assertIsNone(setup["take_profit"])
        self.assertIn("1:3", setup["summary_comment"])

    def test_valid_short_setup_with_rr_above_3(self):
        """When resistance is at 102, Entry at 100, SL at 103 (Risk = 3), and Support at 88 (Reward = 12), RR = 4.0 >= 3.0."""
        current_price = 100.0
        levels = {
            "resistances": [
                {
                    "price": 102.0,
                    "top": 102.5,
                    "bottom": 101.8,
                    "touches": 3,
                    "strength_score": 85.0,
                    "smc_type": "ORDER_BLOCK",
                    "smc_label": "OB SUPPLY",
                }
            ],
            "supports": [
                {
                    "price": 88.0,
                    "top": 88.5,
                    "bottom": 87.8,
                    "touches": 2,
                    "strength_score": 75.0,
                    "smc_type": "ORDER_BLOCK",
                    "smc_label": "OB DEMAND",
                }
            ],
            "pivot_points": {"pp": 100.0, "s1": 88.5},
        }
        fvgs = [
            {
                "type": "BEARISH",
                "lower_price": 100.5,
                "upper_price": 102.0,
                "mitigation_status": "FRESH",
                "mitigation_percent": 15,
            }
        ]
        trendlines = []
        liquidity = {
            "sweeps": [
                {
                    "direction": "SHORT",
                    "levelPrice": 102.4,
                    "desc": "Хибний пробій хаю",
                    "oiConfirmed": True,
                }
            ]
        }
        structure = {"trend": "BEARISH", "summary": "Низхідний тренд"}
        oi_summary = {
            "oi_status": "INCREASING",
            "deltas": {"5m": {"delta_pct": 0.35}},
        }

        setup = generate_trade_setup(
            coin="SOL",
            interval="5m",
            current_price=current_price,
            candles=self.candles,
            levels=levels,
            fvgs=fvgs,
            trendlines=trendlines,
            liquidity=liquidity,
            structure=structure,
            oi_summary=oi_summary,
            min_rr_threshold=3.0,
        )

        self.assertEqual(setup["action"], "LOOK_FOR_SHORT")
        self.assertEqual(setup["direction"], "SHORT")
        self.assertIsNotNone(setup["entry_price"])
        self.assertIsNotNone(setup["entry_range"])
        self.assertIsNotNone(setup["stop_loss"])
        self.assertIsNotNone(setup["take_profit"])
        self.assertGreaterEqual(setup["risk_reward"], 3.0)
        self.assertIn("ШОРТ", setup["summary_comment"])

    def test_rejection_when_price_far_from_poi(self):
        """When price is far from any support/FVG/sweep (chasing price in the air), setup must be WAIT."""
        current_price = 100.0
        levels = {
            "supports": [{"price": 85.0, "top": 85.5, "bottom": 84.5, "touches": 2}],
            "resistances": [{"price": 115.0, "top": 115.5, "bottom": 114.5, "touches": 2}],
        }
        setup = generate_trade_setup(
            coin="BTC",
            interval="5m",
            current_price=current_price,
            candles=self.candles,
            levels=levels,
            fvgs=[],
            trendlines=[],
            liquidity={"sweeps": []},
            structure={"trend": "BULLISH"},
        )
        self.assertEqual(setup["action"], "WAIT")
        self.assertIn("поза зоною", setup["summary_comment"])

    def test_rejection_when_first_obstacle_blocks_rr(self):
        """When immediate resistance is right ahead (e.g. at 101.5), it blocks achieving 1:3 before hitting resistance."""
        current_price = 100.0
        levels = {
            "supports": [{"price": 99.2, "top": 99.5, "bottom": 99.0, "touches": 3}],
            "resistances": [
                {"price": 101.2, "top": 101.5, "bottom": 101.0, "touches": 3},  # Major obstacle only 1.2% ahead!
                {"price": 115.0, "top": 115.5, "bottom": 114.5, "touches": 2},  # Distant resistance
            ],
        }
        setup = generate_trade_setup(
            coin="ETH",
            interval="5m",
            current_price=current_price,
            candles=self.candles,
            levels=levels,
            fvgs=[],
            trendlines=[],
            liquidity={"sweeps": []},
            structure={"trend": "BULLISH"},
            min_rr_threshold=3.0,
        )
        self.assertEqual(setup["action"], "WAIT")
        self.assertIn("блокує рух", setup["summary_comment"])


if __name__ == "__main__":
    unittest.main()
