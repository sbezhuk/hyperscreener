import asyncio
import unittest
from app.reconnect_manager import (
    BackoffConfig,
    ExponentialBackoff,
    ReconnectManager,
    ConnectionState
)


class TestReconnectManager(unittest.IsolatedAsyncioTestCase):

    def test_backoff_algorithm_progression(self):
        """
        Verify exponential backoff requirements:
        - Initial interval: 1s
        - Factor: 2x
        - Max interval: 60s
        - Jitter bounded within jitter_ratio
        """
        config = BackoffConfig(
            initial_interval=1.0,
            multiplier=2.0,
            max_interval=60.0,
            jitter_ratio=0.25
        )
        backoff = ExponentialBackoff(config)

        # Attempt 0: nominal 1.0, jitter [0, 0.25] -> [1.0, 1.25]
        d0 = backoff.next_delay()
        self.assertGreaterEqual(d0, 1.0)
        self.assertLessEqual(d0, 1.25)
        self.assertEqual(backoff.attempt, 1)

        # Attempt 1: nominal 2.0, jitter [0, 0.5] -> [2.0, 2.5]
        d1 = backoff.next_delay()
        self.assertGreaterEqual(d1, 2.0)
        self.assertLessEqual(d1, 2.5)

        # Attempt 2: nominal 4.0, jitter [0, 1.0] -> [4.0, 5.0]
        d2 = backoff.next_delay()
        self.assertGreaterEqual(d2, 4.0)
        self.assertLessEqual(d2, 5.0)

        # Attempt 3: nominal 8.0
        d3 = backoff.next_delay()
        self.assertGreaterEqual(d3, 8.0)
        self.assertLessEqual(d3, 10.0)

        # Attempt 4: nominal 16.0
        d4 = backoff.next_delay()
        self.assertGreaterEqual(d4, 16.0)
        self.assertLessEqual(d4, 20.0)

        # Attempt 5: nominal 32.0
        d5 = backoff.next_delay()
        self.assertGreaterEqual(d5, 32.0)
        self.assertLessEqual(d5, 40.0)

        # Attempt 6: nominal 64 -> capped at max_interval (60.0)
        d6 = backoff.next_delay()
        self.assertGreaterEqual(d6, 60.0)
        self.assertLessEqual(d6, 60.0)

        # Attempt 10: remains capped at 60.0
        for _ in range(4):
            backoff.next_delay()
        d10 = backoff.next_delay()
        self.assertEqual(d10, 60.0)

    def test_backoff_reset(self):
        """Verify resetting counter after successful connection."""
        backoff = ExponentialBackoff(BackoffConfig(initial_interval=1.0, multiplier=2.0))
        for _ in range(5):
            backoff.next_delay()
        self.assertEqual(backoff.attempt, 5)

        backoff.reset()
        self.assertEqual(backoff.attempt, 0)
        d_after_reset = backoff.next_delay()
        self.assertGreaterEqual(d_after_reset, 1.0)
        self.assertLessEqual(d_after_reset, 1.25)

    async def test_lifecycle_states_and_callbacks(self):
        """Verify state transitions: Disconnected -> Connected -> Reconnecting -> Failed."""
        states_recorded = []

        def callback(state, details):
            states_recorded.append((state, details.get("reason") or details.get("message")))

        mgr = ReconnectManager(
            name="TestWS",
            config=BackoffConfig(max_consecutive_failures=3),
            on_state_change=callback
        )
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)
        self.assertFalse(mgr.is_connected)

        # 1. Connect
        await mgr.on_connected()
        self.assertEqual(mgr.state, ConnectionState.CONNECTED)
        self.assertTrue(mgr.is_connected)

        # 2. Unexpected Disconnect
        await mgr.on_disconnected(reason="Network unreachable", error=OSError("No route to host"))
        self.assertEqual(mgr.state, ConnectionState.RECONNECTING)
        self.assertFalse(mgr.is_connected)

        # 3. Retry 1
        d1 = await mgr.prepare_next_retry(OSError("Timeout 1"))
        self.assertEqual(mgr.state, ConnectionState.RECONNECTING)
        self.assertEqual(mgr.consecutive_failures, 1)
        self.assertGreaterEqual(d1, 1.0)

        # Retry 2
        d2 = await mgr.prepare_next_retry(OSError("Timeout 2"))
        self.assertEqual(mgr.state, ConnectionState.RECONNECTING)
        self.assertEqual(mgr.consecutive_failures, 2)
        self.assertGreaterEqual(d2, 2.0)

        # Retry 3: exceeds max_consecutive_failures (3) -> Transitions to FAILED
        d3 = await mgr.prepare_next_retry(OSError("Timeout 3"))
        self.assertEqual(mgr.state, ConnectionState.FAILED)
        self.assertEqual(mgr.consecutive_failures, 3)

        # 4. Successful recovery resets state and failure count
        await mgr.on_connected()
        self.assertEqual(mgr.state, ConnectionState.CONNECTED)
        self.assertEqual(mgr.consecutive_failures, 0)

        diag = mgr.get_diagnostics()
        self.assertEqual(diag["total_connects"], 2)
        self.assertEqual(diag["total_disconnects"], 1)

    async def test_manual_disconnect_and_reconnect(self):
        """Verify user manual disconnect halts retries, and manual reconnect resumes."""
        mgr = ReconnectManager(name="TestManual")
        await mgr.on_connected()

        # User clicks disconnect
        await mgr.manual_disconnect(reason="User clicked pause")
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)
        self.assertTrue(mgr.is_manual_disconnect)

        # Further disconnect notification does not switch state to RECONNECTING
        await mgr.on_disconnected(reason="Socket closed")
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)

        # User clicks reconnect
        await mgr.manual_reconnect()
        self.assertFalse(mgr.is_manual_disconnect)
        self.assertEqual(mgr.state, ConnectionState.RECONNECTING)
        self.assertEqual(mgr.backoff.attempt, 0)

    async def test_wait_before_retry_cancellation(self):
        """Verify that wake_event cancels non-blocking sleep early."""
        mgr = ReconnectManager(name="TestWake")

        # Start a 10-second wait in the background
        start_time = asyncio.get_event_loop().time()

        wait_task = asyncio.create_task(mgr.wait_before_retry(10.0))
        # Trigger wake after 50ms
        await asyncio.sleep(0.05)
        mgr.trigger_wake()

        finished_normally = await wait_task
        elapsed = asyncio.get_event_loop().time() - start_time

        self.assertFalse(finished_normally)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
