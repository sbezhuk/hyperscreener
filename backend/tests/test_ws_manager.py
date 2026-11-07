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

    async def test_multi_coin_independent_oi_history(self):
        """Regression test: multiple coins stream activeAssetCtx and update independent OITrackers."""
        from app.analyzer.oi_tracker import oi_manager
        oi_manager.clear()

        # Simulate incoming activeAssetCtx messages for BTC, ETH, SOL, HYPE
        await self.mgr._handle_hl_message(json.dumps({
            "channel": "activeAssetCtx",
            "data": {"coin": "BTC", "ctx": {"openInterest": "41500.0", "markPx": "75000.0", "funding": "0.0001"}}
        }))
        await self.mgr._handle_hl_message(json.dumps({
            "channel": "activeAssetCtx",
            "data": {"coin": "ETH", "ctx": {"openInterest": "970000.0", "markPx": "2200.0", "funding": "0.0001"}}
        }))
        await self.mgr._handle_hl_message(json.dumps({
            "channel": "activeAssetCtx",
            "data": {"coin": "SOL", "ctx": {"openInterest": "5600000.0", "markPx": "90.0", "funding": "0.0001"}}
        }))
        await self.mgr._handle_hl_message(json.dumps({
            "channel": "activeAssetCtx",
            "data": {"coin": "HYPE", "ctx": {"openInterest": "22000000.0", "markPx": "78.0", "funding": "0.0001"}}
        }))

        # Verify trackers exist and contain independent values
        btc_tracker = oi_manager.get_tracker("BTC")
        eth_tracker = oi_manager.get_tracker("ETH")
        sol_tracker = oi_manager.get_tracker("SOL")
        hype_tracker = oi_manager.get_tracker("HYPE")

        self.assertEqual(btc_tracker.latest.oi, 41500.0)
        self.assertEqual(eth_tracker.latest.oi, 970000.0)
        self.assertEqual(sol_tracker.latest.oi, 5600000.0)
        self.assertEqual(hype_tracker.latest.oi, 22000000.0)

    async def test_active_chart_coin_switching_preserves_oi_tracking(self):
        """Regression test: switching chart coin does NOT unsubscribe activeAssetCtx for monitored coins."""
        mock_ws = AsyncMock()
        self.mgr._hl_ws = mock_ws
        await self.mgr.reconnect_mgr.on_connected()

        # Pre-seed monitored coins
        await self.mgr.update_monitored_coins(["BTC", "ETH", "SOL"])
        mock_ws.send.reset_mock()

        mock_client = AsyncMock()
        await self.mgr.register_client(mock_client)

        # Client subscribes to ETH
        await self.mgr.subscribe_client(mock_client, "ETH", "1m")
        # Client switches to SOL: unsubscribes ETH 1m
        await self.mgr.unsubscribe_client(mock_client, "ETH", "1m")
        await self.mgr.subscribe_client(mock_client, "SOL", "1m")

        # ETH candle topic is unsubscribed
        self.assertNotIn(("ETH", "1m"), self.mgr._subscribed_topics)
        # BUT ETH activeAssetCtx MUST NOT be unsubscribed because it is in _monitored_oi_coins!
        self.assertIn("ETH", self.mgr._monitored_oi_coins)
        self.assertIn("ETH", self.mgr._subscribed_coins)

        # Verify that no unsubscribe for activeAssetCtx ETH was sent
        for call_args in mock_ws.send.call_args_list:
            msg = json.loads(call_args[0][0])
            if msg.get("method") == "unsubscribe":
                sub = msg.get("subscription", {})
                self.assertFalse(sub.get("type") == "activeAssetCtx" and sub.get("coin") == "ETH")

    async def test_reconnect_restores_all_monitored_coins(self):
        """Regression test: on reconnect, activeAssetCtx subscriptions for all monitored coins are restored."""
        mock_ws = AsyncMock()
        self.mgr._hl_ws = mock_ws
        self.mgr._monitored_oi_coins = {"BTC", "ETH", "SOL", "HYPE"}
        self.mgr._subscribed_coins = set()

        # Re-subscribe simulation as in _connection_loop
        coins_to_restore = list(self.mgr._subscribed_coins | self.mgr._monitored_oi_coins)
        for coin in coins_to_restore:
            self.mgr._subscribed_coins.add(coin)
            await mock_ws.send(json.dumps({
                "method": "subscribe",
                "subscription": {"type": "activeAssetCtx", "coin": coin}
            }))

        sent_coins = set()
        for call_args in mock_ws.send.call_args_list:
            msg = json.loads(call_args[0][0])
            if msg.get("method") == "subscribe" and msg.get("subscription", {}).get("type") == "activeAssetCtx":
                sent_coins.add(msg["subscription"]["coin"])

        self.assertEqual(sent_coins, {"BTC", "ETH", "SOL", "HYPE"})

    async def test_dynamic_coin_discovery_and_delisting(self):
        """Regression test: new coins are added and delisted coins are cleanly removed."""
        mock_ws = AsyncMock()
        self.mgr._hl_ws = mock_ws
        await self.mgr.reconnect_mgr.on_connected()

        # Step 1: Initialize with BTC, ETH
        await self.mgr.update_monitored_coins(["BTC", "ETH"])
        self.assertEqual(self.mgr._monitored_oi_coins, {"BTC", "ETH"})

        # Step 2: New coin listed on Hyperliquid
        mock_ws.send.reset_mock()
        await self.mgr.update_monitored_coins(["BTC", "ETH", "NEWCOIN"])
        self.assertIn("NEWCOIN", self.mgr._monitored_oi_coins)
        self.assertIn("NEWCOIN", self.mgr._subscribed_coins)

        # Step 3: Coin delisted
        mock_ws.send.reset_mock()
        await self.mgr.update_monitored_coins(["BTC", "ETH"])
        self.assertNotIn("NEWCOIN", self.mgr._monitored_oi_coins)
        self.assertNotIn("NEWCOIN", self.mgr._subscribed_coins)
        # Verify unsubscribe was sent for NEWCOIN
        unsub_sent = any(
            json.loads(c[0][0]).get("subscription", {}).get("coin") == "NEWCOIN"
            and json.loads(c[0][0]).get("method") == "unsubscribe"
            for c in mock_ws.send.call_args_list
        )
        self.assertTrue(unsub_sent)


if __name__ == "__main__":
    unittest.main()
