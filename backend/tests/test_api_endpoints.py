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
