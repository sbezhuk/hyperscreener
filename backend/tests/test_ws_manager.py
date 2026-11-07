import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ws_manager import HyperliquidWSManager
from app.reconnect_manager import ConnectionState


class TestHyperliquidWSManager(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mgr = HyperliquidWSManager()

    async def asyncTearDown(self):
        await self.mgr.stop()

    async def test_client_registration_and_subscription(self):
        """Verify client registration and topic tracking without duplicate Hyperliquid subscriptions."""
        mock_ws_1 = AsyncMock()
        mock_ws_2 = AsyncMock()

        await self.mgr.register_client(mock_ws_1)
        await self.mgr.register_client(mock_ws_2)
        self.assertEqual(len(self.mgr._active_clients), 2)

        # Client 1 subscribes to ETH 5m
        await self.mgr.subscribe_client(mock_ws_1, "ETH", "5m")
        self.assertIn(("ETH", "5m"), self.mgr._subscribed_topics)
        self.assertIn(("ETH", "5m"), self.mgr._client_subs[mock_ws_1])

        # Client 2 also subscribes to ETH 5m (should NOT duplicate topic in _subscribed_topics)
        await self.mgr.subscribe_client(mock_ws_2, "ETH", "5m")
        self.assertEqual(len(self.mgr._subscribed_topics), 1)

        # Client 1 unsubscribes -> topic still needed for Client 2
        await self.mgr.unsubscribe_client(mock_ws_1, "ETH", "5m")
        self.assertIn(("ETH", "5m"), self.mgr._subscribed_topics)

        # Client 2 unregisters -> topic now has 0 subscribers and is removed
        await self.mgr.unregister_client(mock_ws_2)
        self.assertNotIn(("ETH", "5m"), self.mgr._subscribed_topics)

    async def test_broadcast_status_on_state_change(self):
        """Verify that state changes broadcast the correct JSON to active clients."""
        mock_client = AsyncMock()
        await self.mgr.register_client(mock_client)

        await self.mgr._on_connection_state_change(
            ConnectionState.RECONNECTING,
            {"attempt": 2, "delay": 2.5, "reason": "Network test"}
        )

        mock_client.send_text.assert_called_once()
        raw_sent = mock_client.send_text.call_args[0][0]
        data = json.loads(raw_sent)
        self.assertEqual(data["type"], "ws_status")
        self.assertEqual(data["status"], "reconnecting")
        self.assertEqual(data["attempt"], 2)
        self.assertEqual(data["next_retry_delay"], 2.5)

    async def test_manual_disconnect_and_reconnect(self):
        """Verify manual disconnect halts reconnection and manual reconnect resumes."""
        mock_client = AsyncMock()
        await self.mgr.register_client(mock_client)

        await self.mgr.manual_disconnect()
        self.assertEqual(self.mgr.state, ConnectionState.DISCONNECTED)
        self.assertTrue(self.mgr.reconnect_mgr.is_manual_disconnect)

        await self.mgr.manual_reconnect()
        self.assertEqual(self.mgr.state, ConnectionState.RECONNECTING)
        self.assertFalse(self.mgr.reconnect_mgr.is_manual_disconnect)

    async def test_heartbeat_watchdog_timeout(self):
        """Verify watchdog closes stale websocket if no message received within timeout."""
        mock_ws = AsyncMock()
        self.mgr._hl_ws = mock_ws
        self.mgr._running = True
        await self.mgr.reconnect_mgr.on_connected()

        # Simulate old message (50 seconds ago, timeout is 45s)
        self.mgr._last_received_time = asyncio.get_event_loop().time() - 50.0
        self.mgr._heartbeat_interval = 0.05
        self.mgr._heartbeat_timeout = 0.02

        watchdog_task = asyncio.create_task(self.mgr._heartbeat_watchdog(mock_ws))
        await asyncio.sleep(0.1)
        watchdog_task.cancel()

        mock_ws.close.assert_called()

    def test_candle_cache_update_and_sweep_detection(self):
        """Verify live candle update cache and false breakout detection integrity."""
        # Set up level
        self.mgr.update_levels(
            coin="ETH",
            interval="5m",
            resistances=[{"price": 3000.0, "center_price": 3000.0}],
            supports=[{"price": 2800.0, "center_price": 2800.0}]
        )

        # Candle pierces resistance to 3015.0 (+0.5%) and closes at 2990.0
        sweep_candle = {
            "time": 1700000300,
            "open": 2980.0,
            "high": 3015.0,
            "low": 2975.0,
            "close": 2990.0,
            "volume": 500.0
        }

        detected = self.mgr._detect_live_sweep("ETH", "5m", sweep_candle)
        self.assertIsNotNone(detected)
        self.assertEqual(detected["type"], "bearish_sweep")
        self.assertEqual(detected["direction"], "SHORT")
        self.assertEqual(detected["levelPrice"], 3000.0)
        self.assertEqual(detected["sweepPrice"], 3015.0)


if __name__ == "__main__":
    unittest.main()
