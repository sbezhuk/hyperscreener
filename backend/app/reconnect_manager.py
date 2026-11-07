import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger("hyperscreener.reconnect")


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class BackoffConfig:
    """
    Configuration parameters for Exponential Backoff with Jitter:
    - initial_interval: 1.0 second (Requirement 1.2: initial interval = 1s)
    - multiplier: 2.0 (Requirement 1.2: interval doubles each attempt)
    - max_interval: 60.0 seconds (Requirement 1.2: maximum interval = 60s)
    - jitter_ratio: 0.25 (random jitter up to 25% of interval to avoid thundering herd)
    - max_consecutive_failures: 10 (transitions to FAILED if persistent failure, still re-tryable)
    """
    initial_interval: float = 1.0
    multiplier: float = 2.0
    max_interval: float = 60.0
    jitter_ratio: float = 0.25
    max_consecutive_failures: int = 10


class ExponentialBackoff:
    """
    Computes non-blocking exponential backoff intervals with randomized jitter.
    Formula:
        nominal = min(max_interval, initial_interval * (multiplier ** attempt))
        jitter = random.uniform(0, nominal * jitter_ratio)
        delay = min(max_interval, nominal + jitter)
    """

    def __init__(self, config: Optional[BackoffConfig] = None):
        self.config = config or BackoffConfig()
        self._attempt = 0

    @property
    def attempt(self) -> int:
        return self._attempt

    def reset(self):
        """Resets retry counter back to zero after successful connection."""
        self._attempt = 0

    def calculate_delay(self, attempt: Optional[int] = None) -> float:
        """
        Calculates the delay for a given attempt number (or current attempt)
        with exponential growth and random jitter, bounded by max_interval.
        """
        k = self._attempt if attempt is None else attempt
        nominal = min(
            self.config.max_interval,
            self.config.initial_interval * (self.config.multiplier ** k)
        )
        jitter = random.uniform(0.0, nominal * self.config.jitter_ratio)
        total_delay = min(self.config.max_interval, nominal + jitter)
        return round(total_delay, 3)

    def next_delay(self) -> float:
        """Computes current delay and increments internal attempt counter."""
        delay = self.calculate_delay(self._attempt)
        self._attempt += 1
        return delay

    def peek_next_delay(self) -> float:
        """Inspects what next delay will be without incrementing attempt."""
        return self.calculate_delay(self._attempt)


class ReconnectManager:
    """
    Async connection lifecycle and auto-reconnection manager.
    Handles:
    - State tracking: Connected, Disconnected, Reconnecting, Failed.
    - Exponential backoff with jitter and attempt resets.
    - Non-blocking async execution.
    - Single-flight protection against duplicate reconnect loops.
    - Cancellation on manual user disconnect.
    - Detailed event logging and uptime/downtime diagnostics.
    """

    def __init__(
        self,
        name: str = "ExchangeWS",
        config: Optional[BackoffConfig] = None,
        on_state_change: Optional[Callable[[ConnectionState, Dict[str, Any]], Any]] = None
    ):
        self.name = name
        self.config = config or BackoffConfig()
        self.backoff = ExponentialBackoff(self.config)
        self._state = ConnectionState.DISCONNECTED
        self._is_manual_disconnect = False
        self._lock = asyncio.Lock()
        self._wake_event = asyncio.Event()

        # Callbacks
        self._state_callbacks: List[Callable[[ConnectionState, Dict[str, Any]], Any]] = []
        if on_state_change:
            self._state_callbacks.append(on_state_change)

        # Diagnostics & Metrics
        self._stats = {
            "total_connects": 0,
            "total_disconnects": 0,
            "consecutive_failures": 0,
            "connected_at": None,
            "disconnected_at": None,
            "total_downtime_seconds": 0.0,
            "last_error": None,
            "last_error_time": None,
            "last_retry_delay": 0.0,
        }

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def is_manual_disconnect(self) -> bool:
        return self._is_manual_disconnect

    @property
    def consecutive_failures(self) -> int:
        return self._stats["consecutive_failures"]

    def add_state_callback(self, cb: Callable[[ConnectionState, Dict[str, Any]], Any]):
        if cb not in self._state_callbacks:
            self._state_callbacks.append(cb)

    async def _emit_state_change(self, details: Optional[Dict[str, Any]] = None):
        info = details or {}
        info.update({
            "state": self._state.value,
            "timestamp": time.time(),
            "name": self.name,
            "is_manual": self._is_manual_disconnect,
            "consecutive_failures": self._stats["consecutive_failures"],
        })
        for cb in self._state_callbacks:
            try:
                res = cb(self._state, info)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"[{self.name}] Error in state callback: {e}")

    async def on_connected(self):
        """Called when connection is successfully established."""
        async with self._lock:
            now = time.time()
            if self._stats["disconnected_at"]:
                downtime = now - self._stats["disconnected_at"]
                self._stats["total_downtime_seconds"] += max(0.0, downtime)

            self._state = ConnectionState.CONNECTED
            self._is_manual_disconnect = False
            self.backoff.reset()
            self._stats["total_connects"] += 1
            self._stats["consecutive_failures"] = 0
            self._stats["connected_at"] = now
            self._stats["last_error"] = None
            self._wake_event.clear()

            logger.info(
                f"[{self.name}] ✅ Successfully connected! "
                f"(Total connections: {self._stats['total_connects']})"
            )
            await self._emit_state_change({"message": "Connected successfully"})

    async def on_disconnected(self, reason: str = "Connection closed", error: Optional[Exception] = None):
        """Called when connection is unexpectedly lost or closed."""
        async with self._lock:
            now = time.time()
            self._stats["total_disconnects"] += 1
            self._stats["disconnected_at"] = now
            if error:
                self._stats["last_error"] = str(error)
                self._stats["last_error_time"] = now

            if self._is_manual_disconnect:
                self._state = ConnectionState.DISCONNECTED
                logger.info(f"[{self.name}] Disconnected by user request: {reason}")
                await self._emit_state_change({"reason": reason, "manual": True})
            else:
                self._state = ConnectionState.RECONNECTING
                logger.warning(
                    f"[{self.name}] ⚠️ Connection lost: {reason}. "
                    f"Error: {error or 'None'}. Preparing auto-reconnection..."
                )
                await self._emit_state_change({"reason": reason, "error": str(error) if error else None})

    async def prepare_next_retry(self, error: Optional[Exception] = None) -> float:
        """
        Calculates exponential backoff delay for the next retry attempt.
        Updates failure count and transitions to FAILED if max retries exceeded.
        """
        async with self._lock:
            self._stats["consecutive_failures"] += 1
            now = time.time()
            if error:
                self._stats["last_error"] = str(error)
                self._stats["last_error_time"] = now

            if self._stats["consecutive_failures"] >= self.config.max_consecutive_failures:
                self._state = ConnectionState.FAILED
                logger.error(
                    f"[{self.name}] ❌ Maximum consecutive failures ({self.config.max_consecutive_failures}) reached. "
                    f"State changed to FAILED. Last error: {self._stats['last_error']}"
                )
            else:
                self._state = ConnectionState.RECONNECTING

            delay = self.backoff.next_delay()
            self._stats["last_retry_delay"] = delay

            logger.info(
                f"[{self.name}] 🔄 Retry attempt #{self._stats['consecutive_failures']} "
                f"(backoff: {delay:.2f}s). State: {self._state.value.upper()}"
            )

            await self._emit_state_change({
                "attempt": self._stats["consecutive_failures"],
                "delay": delay,
                "error": str(error) if error else None
            })
            return delay

    async def wait_before_retry(self, delay: float) -> bool:
        """
        Non-blocking wait for `delay` seconds.
        Can be cancelled immediately if manual disconnect or manual reconnect is triggered!
        Returns True if delay finished normally, False if interrupted by wake event.
        """
        try:
            # wait for wake event or timeout
            await asyncio.wait_for(self._wake_event.wait(), timeout=delay)
            # If wake event fired, clear it and return False
            self._wake_event.clear()
            return False
        except asyncio.TimeoutError:
            # Normal timeout elapsed
            return True

    def trigger_wake(self):
        """Wakes up any sleeping reconnection loop immediately."""
        self._wake_event.set()

    async def manual_disconnect(self, reason: str = "User manual disconnect"):
        """User-initiated manual disconnect. Stops auto-reconnect attempts."""
        async with self._lock:
            self._is_manual_disconnect = True
            self._state = ConnectionState.DISCONNECTED
            self._stats["disconnected_at"] = time.time()
            self._wake_event.set()
            logger.info(f"[{self.name}] 🛑 Manual disconnect requested: {reason}")
            await self._emit_state_change({"reason": reason, "manual": True})

    async def manual_reconnect(self):
        """User-initiated manual reconnect. Resets backoff and wakes reconnect loop immediately."""
        async with self._lock:
            self._is_manual_disconnect = False
            self.backoff.reset()
            self._stats["consecutive_failures"] = 0
            self._state = ConnectionState.RECONNECTING
            self._wake_event.set()
            logger.info(f"[{self.name}] 🔁 Manual reconnect requested: resetting backoff and initiating connection.")
            await self._emit_state_change({"reason": "Manual reconnect", "manual": False})

    def get_diagnostics(self) -> Dict[str, Any]:
        """Returns comprehensive diagnostic and telemetry status."""
        now = time.time()
        uptime = (now - self._stats["connected_at"]) if self.is_connected and self._stats["connected_at"] else 0.0
        downtime = self._stats["total_downtime_seconds"]
        if not self.is_connected and self._stats["disconnected_at"]:
            downtime += max(0.0, now - self._stats["disconnected_at"])

        return {
            "name": self.name,
            "state": self._state.value,
            "is_connected": self.is_connected,
            "is_manual_disconnect": self._is_manual_disconnect,
            "current_attempt": self.backoff.attempt,
            "consecutive_failures": self._stats["consecutive_failures"],
            "max_consecutive_failures": self.config.max_consecutive_failures,
            "next_retry_delay": self._stats["last_retry_delay"],
            "total_connects": self._stats["total_connects"],
            "total_disconnects": self._stats["total_disconnects"],
            "uptime_seconds": round(uptime, 2),
            "total_downtime_seconds": round(downtime, 2),
            "connected_at": self._stats["connected_at"],
            "disconnected_at": self._stats["disconnected_at"],
            "last_error": self._stats["last_error"],
            "last_error_time": self._stats["last_error_time"],
        }
