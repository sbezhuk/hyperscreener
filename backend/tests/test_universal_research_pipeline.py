import unittest
import asyncio
import os
import shutil
import tempfile
import time
from unittest.mock import patch, AsyncMock
from app.research.pipeline import (
    discover_available_assets,
    discover_supported_timeframes,
    get_timeframe_step_seconds,
    get_htf_for_timeframe,
    validate_candle_data_quality,
    get_single_dataset,
    fetch_research_universe,
    MarketDiscoveryError,
    set_custom_cache_dir,
)


class TestUniversalResearchPipeline(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        set_custom_cache_dir(self.test_dir)

    def tearDown(self):
        set_custom_cache_dir(None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _generate_valid_candles(self, count=100, interval="15m", start_time=1700000000):
        step = get_timeframe_step_seconds(interval)
        candles = []
        for i in range(count):
            t = start_time + i * step
            candles.append({
                "time": t,
                "open": 100.0 + i * 0.1,
                "high": 100.0 + i * 0.1 + 1.0,
                "low": 100.0 + i * 0.1 - 1.0,
                "close": 100.0 + i * 0.1 + 0.5,
                "volume": 1000.0,
            })
        return candles

    async def test_1_new_asset_appears_dynamically_in_pipeline(self):
        """1. Newly listed asset on Hyperliquid automatically appears in Research Pipeline without hardcoding."""
        mock_universe = [
            {"name": "BTC", "markPrice": 70000.0, "volume24h": 500000000.0, "isDelisted": False},
            {"name": "ETH", "markPrice": 2500.0, "volume24h": 200000000.0, "isDelisted": False},
            {"name": "NEW_TOKEN_XYZ", "markPrice": 1.5, "volume24h": 50000000.0, "isDelisted": False},
        ]
        with patch("app.research.pipeline.hl_client.get_meta_and_contexts", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_universe
            assets = await discover_available_assets(force_refresh=True)
            names = [a["name"] for a in assets]
            self.assertIn("NEW_TOKEN_XYZ", names, "Newly listed token must be automatically discovered")
            self.assertEqual(len(assets), 3)

    async def test_2_delisted_or_dead_assets_excluded(self):
        """2. Delisted or zero-price assets are filtered out from the active universe."""
        mock_universe = [
            {"name": "BTC", "markPrice": 70000.0, "volume24h": 500000000.0, "isDelisted": False},
            {"name": "DEAD_TOKEN", "markPrice": 0.0, "volume24h": 0.0, "isDelisted": False},
            {"name": "OLD_DELISTED", "markPrice": 10.0, "volume24h": 100000.0, "isDelisted": True},
        ]
        with patch("app.research.pipeline.hl_client.get_meta_and_contexts", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_universe
            assets = await discover_available_assets(force_refresh=True)
            names = [a["name"] for a in assets]
            self.assertIn("BTC", names)
            self.assertNotIn("DEAD_TOKEN", names, "Zero mark price instruments must be excluded")
            self.assertNotIn("OLD_DELISTED", names, "Delisted instruments must be excluded")

    def test_3_supported_timeframes_discovery(self):
        """3. Universal supported timeframes include all exchange capabilities without phase fragmentation."""
        tfs = discover_supported_timeframes()
        self.assertIn("1m", tfs)
        self.assertIn("5m", tfs)
        self.assertIn("15m", tfs)
        self.assertIn("1h", tfs)
        self.assertIn("4h", tfs)
        self.assertIn("1d", tfs)
        # Check step seconds helper
        self.assertEqual(get_timeframe_step_seconds("15m"), 900)
        self.assertEqual(get_timeframe_step_seconds("1h"), 3600)
        # Check HTF hierarchy mapping
        self.assertEqual(get_htf_for_timeframe("15m"), "1h")
        self.assertEqual(get_htf_for_timeframe("1h"), "4h")
        self.assertEqual(get_htf_for_timeframe("4h"), "1d")

    async def test_4_missing_data_for_one_timeframe_does_not_halt_pipeline(self):
        """4. Missing candles for one asset/timeframe do not halt execution of other combinations."""
        async def mock_candles(coin, interval, limit=1500, start_time=None, end_time=None):
            if coin == "FAIL_COIN" and interval == "1h":
                return []  # simulate empty response
            return self._generate_valid_candles(100, interval)

        with patch("app.research.pipeline.hl_client.get_candles", side_effect=mock_candles):
            res = await fetch_research_universe(
                coins=["VALID_COIN", "FAIL_COIN"],
                timeframes=["15m", "1h"],
                candle_limit=100,
                force_refresh=True,
            )
            self.assertEqual(res["total_combinations"], 4)
            self.assertEqual(res["successful_datasets"], 3)
            self.assertEqual(res["rejected_count"], 1)
            rejection = res["rejections"][0]
            self.assertEqual(rejection["coin"], "FAIL_COIN")
            self.assertEqual(rejection["timeframe"], "1h")

    async def test_5_cache_isolates_different_assets(self):
        """5. Cache strictly isolates different assets without cross-contamination."""
        btc_candles = self._generate_valid_candles(60, "15m", 1700000000)
        eth_candles = self._generate_valid_candles(60, "15m", 1700000000)
        btc_candles[0]["close"] = 99999.0
        eth_candles[0]["close"] = 3333.0

        async def mock_get(coin, interval, limit=1500, start_time=None, end_time=None):
            return btc_candles if coin == "BTC" else eth_candles

        with patch("app.research.pipeline.hl_client.get_candles", side_effect=mock_get):
            ds_btc = await get_single_dataset("BTC", "15m", force_refresh=True)
            ds_eth = await get_single_dataset("ETH", "15m", force_refresh=True)

            self.assertEqual(ds_btc["candles"][0]["close"], 99999.0)
            self.assertEqual(ds_eth["candles"][0]["close"], 3333.0)
            self.assertNotEqual(ds_btc["candles"][0]["close"], ds_eth["candles"][0]["close"])

    async def test_6_cache_isolates_different_timeframes(self):
        """6. Cache strictly isolates different timeframes for the same asset."""
        c_15m = self._generate_valid_candles(60, "15m", 1700000000)
        c_1h = self._generate_valid_candles(60, "1h", 1700000000)

        async def mock_get(coin, interval, limit=1500, start_time=None, end_time=None):
            return c_15m if interval == "15m" else c_1h

        with patch("app.research.pipeline.hl_client.get_candles", side_effect=mock_get):
            ds_15m = await get_single_dataset("SOL", "15m", force_refresh=True)
            ds_1h = await get_single_dataset("SOL", "1h", force_refresh=True)

            step_15m = ds_15m["candles"][1]["time"] - ds_15m["candles"][0]["time"]
            step_1h = ds_1h["candles"][1]["time"] - ds_1h["candles"][0]["time"]
            self.assertEqual(step_15m, 900)
            self.assertEqual(step_1h, 3600)

    def test_7_data_quality_detects_duplicates(self):
        """7. Quality validator rejects datasets with duplicate timestamps."""
        candles = self._generate_valid_candles(60, "15m")
        candles.append(candles[10].copy())
        q = validate_candle_data_quality(candles, "15m")
        self.assertFalse(q["is_valid"])
        self.assertEqual(q["duplicates_count"], 1)
        self.assertEqual(q["status"], "DATA_QUALITY_REJECTED")

    def test_8_data_quality_detects_missing_fields_and_gaps(self):
        """8. Quality validator detects gaps and missing OHLCV fields."""
        candles = self._generate_valid_candles(60, "15m", 1700000000)
        candles[30]["time"] += 36000  # large jump
        del candles[10]["close"]

        q = validate_candle_data_quality(candles, "15m")
        self.assertFalse(q["is_valid"])
        self.assertGreater(q["missing_fields"], 0)
        self.assertGreater(q["gaps_count"], 0)

    async def test_9_common_discovery_mechanism_used(self):
        """9. Multi-asset pipeline uses common discovery rather than hardcoded lists."""
        mock_universe = [
            {"name": "ALPHA", "markPrice": 10.0, "volume24h": 1000000.0, "isDelisted": False},
            {"name": "BETA", "markPrice": 20.0, "volume24h": 500000.0, "isDelisted": False},
        ]
        with patch("app.research.pipeline.hl_client.get_meta_and_contexts", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_universe
            with patch("app.research.pipeline.hl_client.get_candles", return_value=self._generate_valid_candles(60, "15m")):
                res = await fetch_research_universe(
                    coins=None,  # triggers dynamic discovery
                    timeframes=["15m"],
                    candle_limit=60,
                    force_refresh=True,
                )
                self.assertEqual(res["target_coins"], ["ALPHA", "BETA"])
                self.assertEqual(res["assets_count"], 2)

    async def test_10_api_outage_handling_without_false_full_report(self):
        """10. Total API outage is handled gracefully without falsely reporting a complete universe."""
        with patch("app.research.pipeline.hl_client.get_meta_and_contexts", side_effect=Exception("Exchange Network Down")):
            with self.assertRaises(MarketDiscoveryError):
                await discover_available_assets(force_refresh=True)


if __name__ == "__main__":
    unittest.main()
