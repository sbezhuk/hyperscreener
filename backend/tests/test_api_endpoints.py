import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.ws_manager import hl_ws_manager


class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_ws_status_endpoint(self):
        response = self.client.get("/api/ws/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("state", data)
        self.assertIn("diagnostics", data)
        self.assertIn("subscribed_topics", data)

    def test_oi_endpoint(self):
        from app.analyzer.oi_tracker import oi_manager
        oi_manager.record_tick("ETH", 950000.0, 2600.0)
        response = self.client.get("/api/oi?coin=ETH")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        oi_data = data["data"]
        self.assertEqual(oi_data["coin"], "ETH")
        self.assertEqual(oi_data["current_oi"], 950000.0)
        self.assertIn("deltas", oi_data)
        self.assertIn("1m", oi_data["deltas"])
        self.assertIn("5m", oi_data["deltas"])
        self.assertIn("15m", oi_data["deltas"])
        self.assertIn("1h", oi_data["deltas"])

    def test_manual_disconnect_and_reconnect_endpoints(self):
        # Disconnect
        resp_disc = self.client.post("/api/ws/disconnect")
        self.assertEqual(resp_disc.status_code, 200)
        data_disc = resp_disc.json()
        self.assertTrue(data_disc["success"])
        self.assertEqual(data_disc["state"], "disconnected")

        # Reconnect
        resp_rec = self.client.post("/api/ws/reconnect")
        self.assertEqual(resp_rec.status_code, 200)
        data_rec = resp_rec.json()
        self.assertTrue(data_rec["success"])
        self.assertEqual(data_rec["state"], "reconnecting")

    def test_analyze_levels_dynamic_discovery(self):
        from app.analyzer.levels import analyze_levels
        # Test with monotonic downtrend / breaking support
        candles = [
            {"time": 1000 + i * 60, "open": 100.0 - i, "high": 101.0 - i, "low": 99.0 - i, "close": 99.5 - i, "volume": 100.0}
            for i in range(15)
        ]
        res = analyze_levels(candles, interval="5m")
        self.assertIn("resistances", res)
        self.assertIn("supports", res)
        # Verify no KeyError occurred and fields exist
        for s in res["supports"] + res["resistances"]:
            self.assertIn("firstTime", s)
            self.assertIn("latestTime", s)
            self.assertIn("price", s)

    def test_error_mapping_status_codes(self):
        from unittest.mock import patch, AsyncMock
        import httpx

        # 1. TimeoutException -> HTTP 504
        with patch("app.main.hl_client.get_candles", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ReadTimeout("Timeout connecting to Hyperliquid")
            resp = self.client.get("/api/candles?coin=ETH&interval=1d")
            self.assertEqual(resp.status_code, 504)
            self.assertFalse(resp.json()["success"])
            self.assertIn("Таймаут", resp.json()["error"])

        # 2. ConnectError (network error) -> HTTP 502
        with patch("app.main.hl_client.get_candles", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused by peer")
            resp = self.client.get("/api/candles?coin=ETH&interval=1d")
            self.assertEqual(resp.status_code, 502)
            self.assertFalse(resp.json()["success"])
            self.assertIn("Мережева помилка", resp.json()["error"])

        # 3. Empty candles -> HTTP 404
        with patch("app.main.hl_client.get_candles", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = self.client.get("/api/candles?coin=NONEXISTENT&interval=1d")
            self.assertEqual(resp.status_code, 404)
            self.assertFalse(resp.json()["success"])

        # 4. Analysis internal/calc error -> HTTP 500 (NOT 404)
        with patch("app.main.analyze_coin_data", new_callable=AsyncMock) as mock_an:
            mock_an.side_effect = ZeroDivisionError("division by zero in indicator")
            resp = self.client.get("/api/analysis?coin=ETH&interval=1d")
            self.assertEqual(resp.status_code, 500)
            self.assertFalse(resp.json()["success"])
            self.assertIn("Помилка сервера", resp.json()["error"])


if __name__ == "__main__":
    unittest.main()
