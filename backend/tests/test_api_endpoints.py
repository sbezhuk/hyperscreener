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


if __name__ == "__main__":
    unittest.main()
