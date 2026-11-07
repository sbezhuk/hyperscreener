import asyncio
import json
import logging
import time
from typing import Dict, Set, Any, Optional, Tuple, List
import websockets
from fastapi import WebSocket

from .hyperliquid import hl_client
from .analyzer.oi_tracker import oi_manager
from .reconnect_manager import (
    ReconnectManager,
    BackoffConfig,
    ConnectionState
)

logger = logging.getLogger("hyperscreener.ws")
logging.basicConfig(level=logging.INFO)

HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"


class HyperliquidWSManager:
    """
    Direct WebSocket connection manager for Hyperliquid (wss://api.hyperliquid.xyz/ws)
    Features:
    - Point 1.1: Direct streaming of candle and allMids real-time tick data.
    - Point 1.2: Robust Auto-Reconnection Manager with Exponential Backoff (1s -> 2x -> 60s max) + Jitter,
                 heartbeat watchdog, non-blocking async loops, single-flight guard, and manual override.
    - Point 1.3: Real-time on-the-fly sweep detection when candle touches/pierces levels.
    """

    def __init__(self):
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._hl_ws = None
        self._last_received_time: float = 0.0
        self._heartbeat_interval: float = 20.0
        self._heartbeat_timeout: float = 45.0
        self._connection_lock = asyncio.Lock()

        # Reconnect Manager with strict exponential backoff parameters:
        # Base: 1.0s, multiplier: 2.0x, max: 60.0s, jitter: 0.25
        self.reconnect_mgr = ReconnectManager(
            name="HyperliquidWS",
            config=BackoffConfig(
                initial_interval=1.0,
                multiplier=2.0,
                max_interval=60.0,
                jitter_ratio=0.25,
                max_consecutive_failures=15
            ),
            on_state_change=self._on_connection_state_change
        )

        # Frontend client connections
        self._active_clients: Set[WebSocket] = set()
        # client -> set of (coin, interval)
        self._client_subs: Dict[WebSocket, Set[Tuple[str, str]]] = {}

        # Active subscriptions on Hyperliquid WS: set of (coin, interval)
        self._subscribed_topics: Set[Tuple[str, str]] = set()
        # Active coin asset context subscriptions on Hyperliquid WS: set of coin symbols
        self._subscribed_coins: Set[str] = set()
        # Monitored screener coins for continuous background OI tracking
        self._monitored_oi_coins: Set[str] = set()
        self._oi_sync_task: Optional[asyncio.Task] = None

        # Levels cache for live sweep checking: (coin, interval) -> { "resistances": [...], "supports": [...] }
        self._levels_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Recent closed candle cache: (coin, interval) -> previous candle dict
        self._prev_candles: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Avoid duplicate sweep notifications while allowing status updates (POTENTIAL -> CONFIRMED):
        # Maps sweep_sig -> metadata dict (id, status, oiDeltaPct, last_updated_at, etc.)
        self._seen_live_sweeps: Dict[str, Dict[str, Any]] = {}
        self._last_sweeps_cleanup: float = time.time()

    @property
    def is_connected(self) -> bool:
        return self.reconnect_mgr.is_connected

    @property
    def state(self) -> ConnectionState:
        return self.reconnect_mgr.state

    async def start(self):
        """Starts background task to manage Hyperliquid WS connection with single-flight guard."""
        if self._running and self._ws_task and not self._ws_task.done():
            logger.debug("Hyperliquid WS manager is already running.")
            return

        self._running = True
        self._ws_task = asyncio.create_task(self._connection_loop())
        self._oi_sync_task = asyncio.create_task(self._periodic_oi_coins_sync())

    async def stop(self):
        """Stops background tasks and closes connection cleanly."""
        self._running = False
        await self._cleanup_connection()
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._ws_task = None
        if self._oi_sync_task and not self._oi_sync_task.done():
            self._oi_sync_task.cancel()
            try:
                await self._oi_sync_task
            except asyncio.CancelledError:
                pass
        self._oi_sync_task = None
        await self.reconnect_mgr.manual_disconnect(reason="Service shutdown")

    async def manual_disconnect(self):
        """User-initiated manual disconnect. Halts automatic reconnection attempts."""
        logger.info("Manual disconnect requested by user.")
        await self.reconnect_mgr.manual_disconnect(reason="Manual disconnect by user")
        await self._cleanup_connection()

    async def manual_reconnect(self):
        """User-initiated manual reconnect. Resets backoff counter and reconnects immediately."""
        logger.info("Manual reconnect requested by user.")
        await self.reconnect_mgr.manual_reconnect()
        # If connection loop is not active or awaiting retry, wake it or restart it
        if not self._running or self._ws_task is None or self._ws_task.done():
            self._running = True
            self._ws_task = asyncio.create_task(self._connection_loop())
        else:
            self.reconnect_mgr.trigger_wake()

    async def _cleanup_connection(self):
        """Cancels heartbeat watchdog and closes active websocket session."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        self._watchdog_task = None

        if self._hl_ws:
            try:
                await self._hl_ws.close()
            except Exception as e:
                logger.debug(f"Error during WS close: {e}")
        self._hl_ws = None

    def update_levels(self, coin: str, interval: str, resistances: List[Dict[str, Any]], supports: List[Dict[str, Any]]):
        """Updates levels used for instantaneous sweep detection."""
        key = (coin.upper(), interval.lower())
        self._levels_cache[key] = {
            "resistances": resistances or [],
            "supports": supports or [],
            "updatedAt": time.time(),
        }

    # -------------------------------------------------------------
    # Frontend WebSocket Clients Management
    # -------------------------------------------------------------
    async def register_client(self, client: WebSocket):
        self._active_clients.add(client)
        self._client_subs[client] = set()

    async def unregister_client(self, client: WebSocket):
        subs = self._client_subs.pop(client, set())
        if client in self._active_clients:
            self._active_clients.remove(client)

        # Check if any topic has 0 subscribers now
        for coin, interval in subs:
            await self._check_and_unsubscribe_if_unused(coin, interval)

    async def subscribe_client(self, client: WebSocket, coin: str, interval: str):
        coin = coin.upper()
        clean_tf = interval.lower()
        if client not in self._client_subs:
            self._client_subs[client] = set()

        topic = (coin, clean_tf)
        self._client_subs[client].add(topic)

        # If not subscribed to Hyperliquid yet, subscribe now (candle and activeAssetCtx for real-time OI)
        await self._ensure_hl_subscribed(coin, clean_tf)
        await self._ensure_hl_coin_subscribed(coin)

    async def unsubscribe_client(self, client: WebSocket, coin: str, interval: str):
        coin = coin.upper()
        clean_tf = interval.lower()
        topic = (coin, clean_tf)
        if client in self._client_subs and topic in self._client_subs[client]:
            self._client_subs[client].remove(topic)
            await self._check_and_unsubscribe_if_unused(coin, clean_tf)
            await self._check_and_unsubscribe_coin_if_unused(coin)

    async def _check_and_unsubscribe_if_unused(self, coin: str, interval: str):
        topic = (coin, interval)
        has_subscribers = any(topic in subs for subs in self._client_subs.values())
        if not has_subscribers and topic in self._subscribed_topics:
            self._subscribed_topics.remove(topic)
            if self._hl_ws and self.is_connected:
                unsub_msg = {
                    "method": "unsubscribe",
                    "subscription": {
                        "type": "candle",
                        "coin": coin,
                        "interval": interval
                    }
                }
                try:
                    await self._hl_ws.send(json.dumps(unsub_msg))
                except Exception as e:
                    logger.warning(f"Error sending unsubscribe: {e}")

    async def _check_and_unsubscribe_coin_if_unused(self, coin: str):
        # Do not unsubscribe if coin is actively monitored for background screener OI tracking
        if coin in self._monitored_oi_coins:
            return

        has_coin_subscribers = any(
            any(sub_coin == coin for sub_coin, _ in subs)
            for subs in self._client_subs.values()
        )
        if not has_coin_subscribers and coin in self._subscribed_coins:
            self._subscribed_coins.remove(coin)
            if self._hl_ws and self.is_connected:
                unsub_msg = {
                    "method": "unsubscribe",
                    "subscription": {
                        "type": "activeAssetCtx",
                        "coin": coin
                    }
                }
                try:
                    await self._hl_ws.send(json.dumps(unsub_msg))
                except Exception as e:
                    logger.warning(f"Error sending unsubscribe activeAssetCtx: {e}")

    async def _ensure_hl_coin_subscribed(self, coin: str):
        coin = coin.upper()
        # Ensure independent OITracker exists
        oi_manager.get_tracker(coin)
        if coin not in self._subscribed_coins:
            self._subscribed_coins.add(coin)
            if self._hl_ws and self.is_connected:
                sub_msg = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "activeAssetCtx",
                        "coin": coin
                    }
                }
                try:
                    await self._hl_ws.send(json.dumps(sub_msg))
                    logger.info(f"Subscribed to Hyperliquid WS activeAssetCtx: {coin}")
                except Exception as e:
                    logger.warning(f"Error sending subscribe activeAssetCtx: {e}")

    async def update_monitored_coins(self, coins: List[str]):
        """
        Synchronizes the set of active perpetual coins monitored for continuous OI tracking.
        Adds new coins, removes delisted coins, and maintains subscriptions.
        """
        new_set = {c.upper() for c in coins if c}
        added = new_set - self._monitored_oi_coins
        removed = self._monitored_oi_coins - new_set

        if not added and not removed:
            return

        # 1. Handle delisted / removed coins
        for coin in removed:
            self._monitored_oi_coins.discard(coin)
            has_chart_sub = any(
                any(sub_coin == coin for sub_coin, _ in subs)
                for subs in self._client_subs.values()
            )
            if not has_chart_sub and coin in self._subscribed_coins:
                self._subscribed_coins.remove(coin)
                if self._hl_ws and self.is_connected:
                    try:
                        await self._hl_ws.send(json.dumps({
                            "method": "unsubscribe",
                            "subscription": {"type": "activeAssetCtx", "coin": coin}
                        }))
                    except Exception as e:
                        logger.warning(f"Error unsubscribing removed coin {coin}: {e}")

        # 2. Handle newly added coins
        newly_subscribed = []
        for coin in added:
            self._monitored_oi_coins.add(coin)
            # Ensure independent OITracker is initialized
            oi_manager.get_tracker(coin)
            if coin not in self._subscribed_coins:
                self._subscribed_coins.add(coin)
                newly_subscribed.append(coin)

        # Batch send subscriptions if connected
        if newly_subscribed and self._hl_ws and self.is_connected:
            for i, coin in enumerate(newly_subscribed):
                try:
                    await self._hl_ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "activeAssetCtx", "coin": coin}
                    }))
                    if (i + 1) % 50 == 0:
                        await asyncio.sleep(0.02)
                except Exception as e:
                    logger.warning(f"Error subscribing new coin {coin}: {e}")
            logger.info(f"Subscribed {len(newly_subscribed)} new coins for continuous background OI tracking.")

    async def sync_all_screener_coins(self):
        """
        Discovers all active perpetual contracts on Hyperliquid and ensures
        continuous OI tracking without UI dependencies.
        """
        try:
            meta = await hl_client.get_meta_and_contexts()
            active_coin_names = [c["name"] for c in meta if c.get("name")]
            await self.update_monitored_coins(active_coin_names)
        except Exception as e:
            logger.warning(f"Failed to sync screener coins for OI monitoring: {e}")

    async def _periodic_oi_coins_sync(self):
        """
        Background task: runs immediately on startup, then periodically every 300 seconds (5 min)
        to catch newly listed perpetual contracts and maintain subscriptions.
        """
        # Brief pause to let initial WS connect
        await asyncio.sleep(1.0)
        while self._running:
            try:
                await self.sync_all_screener_coins()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in periodic OI sync: {e}")

            try:
                await asyncio.sleep(300.0)
            except asyncio.CancelledError:
                break
                try:
                    await self._hl_ws.send(json.dumps(sub_msg))
                    logger.info(f"Subscribed to Hyperliquid WS activeAssetCtx: {coin}")
                except Exception as e:
                    logger.warning(f"Error sending subscribe activeAssetCtx: {e}")

    async def _ensure_hl_subscribed(self, coin: str, interval: str):
        topic = (coin, interval)
        if topic not in self._subscribed_topics:
            self._subscribed_topics.add(topic)
            if self._hl_ws and self.is_connected:
                sub_msg = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "candle",
                        "coin": coin,
                        "interval": interval
                    }
                }
                try:
                    await self._hl_ws.send(json.dumps(sub_msg))
                    logger.info(f"Subscribed to Hyperliquid WS candle: {coin} {interval}")
                except Exception as e:
                    logger.warning(f"Error sending subscribe: {e}")

    # -------------------------------------------------------------
    # Hyperliquid WebSocket Connection Loop (Auto-Reconnect)
    # -------------------------------------------------------------
    async def _connection_loop(self):
        """
        Continuously maintains connection to Hyperliquid WS with exponential backoff & jitter.
        Ensures non-blocking execution, single-flight protection, and clean lifecycle management.
        """
        async with self._connection_lock:
            while self._running:
                # If manual disconnect was triggered, sleep until manual reconnect or shutdown
                if self.reconnect_mgr.is_manual_disconnect:
                    logger.info("Connection loop idle due to manual disconnect. Waiting for user action...")
                    await self.reconnect_mgr.wait_before_retry(3600.0)
                    continue

                connect_start_time = time.time()
                try:
                    logger.info(f"Connecting to Hyperliquid WebSocket: {HYPERLIQUID_WS_URL} ...")
                    async with websockets.connect(
                        HYPERLIQUID_WS_URL,
                        ping_interval=None,  # We run custom Hyperliquid application-level heartbeat
                        close_timeout=5,
                        max_size=10_000_000
                    ) as ws:
                        self._hl_ws = ws
                        self._last_received_time = time.time()
                        await self.reconnect_mgr.on_connected()

                        # Re-subscribe to all active topics without duplication
                        for coin, interval in list(self._subscribed_topics):
                            sub_msg = {
                                "method": "subscribe",
                                "subscription": {
                                    "type": "candle",
                                    "coin": coin,
                                    "interval": interval
                                }
                            }
                            await ws.send(json.dumps(sub_msg))
                            logger.info(f"Restored subscription candle: {coin} {interval}")

                        coins_to_restore = list(self._subscribed_coins | self._monitored_oi_coins)
                        for i, coin in enumerate(coins_to_restore):
                            self._subscribed_coins.add(coin)
                            sub_ctx = {
                                "method": "subscribe",
                                "subscription": {
                                    "type": "activeAssetCtx",
                                    "coin": coin
                                }
                            }
                            await ws.send(json.dumps(sub_ctx))
                            if (i + 1) % 50 == 0:
                                await asyncio.sleep(0.02)
                        logger.info(f"Restored {len(coins_to_restore)} activeAssetCtx subscriptions upon reconnection.")

                        # Start heartbeat watchdog (pings every 20s, checks silent timeout at 45s)
                        if self._watchdog_task and not self._watchdog_task.done():
                            self._watchdog_task.cancel()
                        self._watchdog_task = asyncio.create_task(self._heartbeat_watchdog(ws))

                        # Receive incoming messages from Hyperliquid
                        async for raw_msg in ws:
                            if not self._running or self.reconnect_mgr.is_manual_disconnect:
                                break
                            self._last_received_time = time.time()
                            await self._handle_hl_message(raw_msg)

                except asyncio.CancelledError:
                    logger.info("Connection task cancelled.")
                    break
                except Exception as e:
                    # Record disconnect and determine whether it was manual
                    session_duration = round(time.time() - connect_start_time, 2)
                    error_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                    await self.reconnect_mgr.on_disconnected(
                        reason=f"Session closed after {session_duration}s ({error_msg})",
                        error=e
                    )
                finally:
                    await self._cleanup_connection()

                if not self._running:
                    break

                if self.reconnect_mgr.is_manual_disconnect:
                    continue

                # Prepare exponential backoff with randomized jitter
                delay = await self.reconnect_mgr.prepare_next_retry()
                logger.info(f"Waiting {delay:.2f}s before next reconnection attempt...")

                # Non-blocking cancelable wait
                await self.reconnect_mgr.wait_before_retry(delay)

        self._hl_ws = None

    async def _heartbeat_watchdog(self, ws):
        """
        Periodically sends Hyperliquid heartbeat ping and detects silent TCP half-open freezes.
        If no pong or message is received within `_heartbeat_timeout`, terminates connection.
        """
        try:
            while self._running and self.is_connected and not self.reconnect_mgr.is_manual_disconnect:
                await asyncio.sleep(self._heartbeat_interval)
                # Send ping
                try:
                    await ws.send(json.dumps({"method": "ping"}))
                except Exception as e:
                    logger.warning(f"Failed to send ping keepalive: {e}")
                    break

                # Watchdog check for stale connection (no message or pong received)
                now = time.time()
                time_since_last_msg = now - self._last_received_time
                if time_since_last_msg > self._heartbeat_timeout:
                    logger.warning(
                        f"⚠️ Heartbeat timeout: No message or pong from Hyperliquid for {time_since_last_msg:.1f}s. "
                        f"Closing stale connection to initiate auto-reconnection."
                    )
                    await ws.close()
                    break
        except (asyncio.CancelledError, Exception):
            pass

    async def _on_connection_state_change(self, state: ConnectionState, details: Dict[str, Any]):
        """Callback from ReconnectManager: broadcasts status update to all connected frontend clients."""
        await self._broadcast_status(
            status=state,
            attempt=details.get("attempt", self.reconnect_mgr.consecutive_failures),
            delay=details.get("delay", 0.0),
            reason=details.get("reason", ""),
            is_manual=details.get("manual", self.reconnect_mgr.is_manual_disconnect)
        )

    async def _broadcast_status(
        self,
        status: ConnectionState,
        attempt: int = 0,
        delay: float = 0.0,
        reason: str = "",
        is_manual: bool = False
    ):
        msg = json.dumps({
            "type": "ws_status",
            "status": status.value if hasattr(status, "value") else str(status),
            "attempt": attempt,
            "next_retry_delay": round(delay, 2),
            "reason": reason,
            "is_manual": is_manual,
            "timestamp": time.time(),
            "diagnostics": self.reconnect_mgr.get_diagnostics()
        })
        dead_clients = []
        for client in list(self._active_clients):
            try:
                await client.send_text(msg)
            except Exception:
                dead_clients.append(client)
        for dc in dead_clients:
            await self.unregister_client(dc)

    # -------------------------------------------------------------
    # Message Dispatching & Real-Time Sweep Detection
    # -------------------------------------------------------------
    async def _handle_hl_message(self, raw_msg: str):
        try:
            data = json.loads(raw_msg)
        except Exception:
            return

        channel = data.get("channel")
        if channel == "pong":
            # Successfully received heartbeat response from Hyperliquid
            return

        if channel == "candle":
            c_data = data.get("data")
            if not c_data:
                return

            coin = c_data.get("s")
            interval = c_data.get("i", "").lower()
            if not coin or not interval:
                return

            candle = {
                "time": int(c_data["t"] / 1000),
                "open": float(c_data["o"]),
                "high": float(c_data["h"]),
                "low": float(c_data["l"]),
                "close": float(c_data["c"]),
                "volume": float(c_data["v"]),
            }

            # Update cache in HyperliquidClient for this coin & interval
            self._update_cache_candle(coin, interval, candle)

            # Live Sweep Detection on the fly!
            live_sweep = self._detect_live_sweep(coin, interval, candle)

            # Forward tick to subscribed frontend clients
            topic = (coin, interval)
            payload = {
                "type": "candle_tick",
                "coin": coin,
                "interval": interval,
                "candle": candle,
                "currentPrice": candle["close"],
                "sweep": live_sweep
            }
            msg_str = json.dumps(payload)

            dead_clients = []
            for client, subs in list(self._client_subs.items()):
                if topic in subs:
                    try:
                        await client.send_text(msg_str)
                    except Exception:
                        dead_clients.append(client)

            for dc in dead_clients:
                await self.unregister_client(dc)

        if channel == "activeAssetCtx":
            asset_data = data.get("data")
            if not asset_data:
                return
            coin = asset_data.get("coin")
            ctx = asset_data.get("ctx", {})
            if not coin or not ctx:
                return

            try:
                oi = float(ctx.get("openInterest", 0.0))
                px = float(ctx.get("markPx", 0.0))
                funding = float(ctx.get("funding", 0.0))
            except (ValueError, TypeError):
                return

            if oi > 0 and px > 0:
                oi_manager.record_tick(coin=coin, oi=oi, price=px)

                # Only format full summary and broadcast to frontend if at least one client is watching this coin
                has_subscribers = any(
                    any(sub_coin == coin for sub_coin, _ in subs)
                    for subs in self._client_subs.values()
                )
                if not has_subscribers:
                    return

                levels = self._get_all_levels_for_coin(coin)
                oi_summary = oi_manager.get_coin_oi_summary(coin=coin, levels=levels)

                payload = {
                    "type": "oi_tick",
                    "coin": coin,
                    "openInterest": oi,
                    "markPrice": px,
                    "fundingRate": funding,
                    "oi_summary": oi_summary,
                    "breakout_signals": oi_summary.get("breakout_signals", [])
                }
                msg_str = json.dumps(payload)

                dead_clients = []
                for client, subs in list(self._client_subs.items()):
                    if any(sub_coin == coin for sub_coin, _ in subs):
                        try:
                            await client.send_text(msg_str)
                        except Exception:
                            dead_clients.append(client)

                for dc in dead_clients:
                    await self.unregister_client(dc)

    def _get_all_levels_for_coin(self, coin: str) -> List[Dict[str, Any]]:
        """Returns consolidated support and resistance levels for this coin across cached timeframes."""
        coin_upper = coin.upper()
        levels: List[Dict[str, Any]] = []
        seen = set()
        for (c, _tf), data in self._levels_cache.items():
            if c == coin_upper and isinstance(data, dict):
                for lvl in data.get("resistances", []) + data.get("supports", []):
                    lid = lvl.get("zone_id") or str(lvl.get("price"))
                    if lid not in seen:
                        seen.add(lid)
                        levels.append(lvl)
        return levels

    def _update_cache_candle(self, coin: str, interval: str, candle: Dict[str, Any]):
        """Updates in-memory candle cache so REST / analysis sees fresh ticks immediately."""
        cache_key_prefix = f"candles:{coin}:{interval}:"
        for key, candles in hl_client._cache.items():
            if key.startswith(cache_key_prefix) and isinstance(candles, list) and candles:
                last = candles[-1]
                if last["time"] == candle["time"]:
                    candles[-1] = candle
                elif candle["time"] > last["time"]:
                    candles.append(candle)
                    if len(candles) > 300:
                        candles.pop(0)

    def _cleanup_live_sweeps_cache(self, now: Optional[float] = None, ttl_seconds: float = 7200.0):
        """
        Prunes live sweeps entries older than 2 hours (ttl_seconds), but preserves active formations
        that are still in POTENTIAL state awaiting confirmation.
        """
        curr_ts = now if now is not None else time.time()
        keys_to_delete = []
        for key, rec in list(self._seen_live_sweeps.items()):
            if isinstance(rec, dict):
                last_updated = rec.get("last_updated_at") or rec.get("created_at") or 0.0
                status = rec.get("status")
                # Do NOT delete active potential formations that still await confirmation within TTL
                if status == "POTENTIAL" and (curr_ts - last_updated) < ttl_seconds:
                    continue
                if (curr_ts - last_updated) >= ttl_seconds:
                    keys_to_delete.append(key)
        for k in keys_to_delete:
            self._seen_live_sweeps.pop(k, None)

    def _detect_live_sweep(
        self,
        coin: str,
        interval: str,
        candle: Dict[str, Any],
        is_closed: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Instantaneous sweep / false breakout detection against active levels on candle close
        with Open Interest (OI) drop confirmation.
        Supports:
        - Single candle wick sweep & close back.
        - Two candle reversal (previous candle broke level, current candle returns and closes on other side).
        - Transition updates (POTENTIAL -> CONFIRMED/UNCONFIRMED) without duplicate alert floods.
        - Strictly forbids final CONFIRMED on unclosed candles until final close verification.
        - Safe TTL cleanup (2h) preventing unbounded memory growth.
        """
        levels = self._levels_cache.get((coin, interval))
        if not levels:
            return None

        resistances = levels.get("resistances", [])
        supports = levels.get("supports", [])

        c_high = candle["high"]
        c_low = candle["low"]
        c_close = candle["close"]
        c_time = candle["time"]

        now_ts = time.time()
        # Periodic cache cleanup every 60 seconds
        if now_ts - self._last_sweeps_cleanup > 60.0:
            self._last_sweeps_cleanup = now_ts
            self._cleanup_live_sweeps_cache()

        from .analyzer.false_breakout import INTERVAL_SECONDS, evaluate_false_breakout_oi
        interval_sec = INTERVAL_SECONDS.get(interval.lower(), 300)

        # Check if candle is closed
        if is_closed is None:
            candle_is_closed = candle.get("is_closed", False) or (now_ts >= c_time + interval_sec)
        else:
            candle_is_closed = is_closed

        prev_c = self._prev_candles.get((coin, interval))
        tracker = oi_manager.get_tracker(coin)

        def _get_live_oi_eval(t_pre: float, t_conf: float, closed_flag: bool):
            test_candles = [
                {"time": t_pre, "close": candle["open"]},
                {"time": t_conf, "close": candle["close"]}
            ]
            return evaluate_false_breakout_oi(
                candles=test_candles,
                breakout_idx=1,
                conf_idx=1,
                interval=interval,
                oi_tracker=tracker,
                coin=coin,
                is_candle_closed=closed_flag,
                cutoff_timestamp=now_ts
            )

        def _process_sweep_state(
            sig_key: str,
            default_id: str,
            sweep_type: str,
            sub_type: str,
            level_px: float,
            sweep_px: float,
            direction: str,
            breakout_time: int,
            conf_time: int,
            base_form_title: str,
            action_desc: str,
            t_pre: float,
        ) -> Optional[Dict[str, Any]]:
            oi_eval = _get_live_oi_eval(t_pre, conf_time, candle_is_closed)
            # An unclosed candle is strictly POTENTIAL until final close verification
            if not candle_is_closed:
                conf_status = "POTENTIAL"
                oi_eval["status"] = "POTENTIAL"
                oi_eval["is_confirmed"] = False
                oi_eval["status_label"] = "Потенційний хибний пробій"
            else:
                conf_status = oi_eval["status"]
            oi_pct = oi_eval["oi_delta_pct"]

            existing = self._seen_live_sweeps.get(sig_key)
            if existing:
                prev_status = existing.get("status")
                prev_pct = existing.get("oiDeltaPct")
                pct_same = (prev_pct is None and oi_pct is None) or (
                    prev_pct is not None and oi_pct is not None and abs(prev_pct - oi_pct) < 0.01
                )
                # If state has not changed and OI delta is identical: suppress duplicate alert
                if prev_status == conf_status and pct_same:
                    return None

            # Neutral factual text phrasing
            if conf_status == "CONFIRMED":
                form_title = f"{base_form_title} (LIVE - Підтверджено OI)"
                desc_oi = f", скорочення OI: {oi_pct:.2f}%"
            elif conf_status == "POTENTIAL":
                form_title = f"{base_form_title} (Потенційний LIVE)"
                desc_oi = f", зміна OI: {oi_pct:+.2f}% (очікується закриття свічки)" if oi_pct is not None else ", очікується закриття свічки"
            else:
                form_title = f"{base_form_title} (LIVE - Непідтверджено)"
                desc_oi = f", зміна OI: {oi_pct:+.2f}%" if oi_pct is not None else ", дані OI відсутні"

            desc = f"{action_desc}{desc_oi}"
            stable_id = existing.get("id") if existing else default_id

            sweep_payload = {
                "id": stable_id,
                "type": sweep_type,
                "subType": sub_type,
                "formation": form_title,
                "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                "sweepPrice": round(sweep_px, 2 if sweep_px > 10 else 4),
                "direction": direction,
                "time": conf_time,
                "breakoutTime": breakout_time,
                "confirmationTime": conf_time,
                "desc": desc,
                "isLive": True,
                "confirmationStatus": conf_status,
                "statusLabel": oi_eval["status_label"],
                "oiConfirmed": oi_eval["is_confirmed"],
                "oiDelta": oi_eval["oi_delta"],
                "oiDeltaPct": oi_eval["oi_delta_pct"],
                "oiReason": oi_eval["reason"],
                "oiReasonDesc": oi_eval["reason_desc"],
            }

            self._seen_live_sweeps[sig_key] = {
                "id": stable_id,
                "status": conf_status,
                "oiDeltaPct": oi_pct,
                "created_at": existing.get("created_at") if existing else now_ts,
                "last_updated_at": now_ts,
                "levelPrice": level_px,
                "candle_time": c_time,
            }
            return sweep_payload

        # 1. Check resistance false breakout / sweeps (Bearish Sweeps -> Short)
        for r in resistances:
            level_px = r.get("center_price", r.get("price"))
            if not level_px:
                continue

            # Invalidate potential resistance sweep if price re-breaks above level on open candle
            wick_sig_key = f"{coin}-{interval}-{c_time}-bearish-wick-{level_px}"
            c2_sig_key = f"{coin}-{interval}-{c_time}-bearish-2c-{level_px}"
            if not candle_is_closed and c_close >= level_px:
                if wick_sig_key in self._seen_live_sweeps and self._seen_live_sweeps[wick_sig_key].get("status") == "POTENTIAL":
                    self._seen_live_sweeps.pop(wick_sig_key, None)
                if c2_sig_key in self._seen_live_sweeps and self._seen_live_sweeps[c2_sig_key].get("status") == "POTENTIAL":
                    self._seen_live_sweeps.pop(c2_sig_key, None)

            # Case A: Pierced above level, currently below level
            if c_high > level_px and c_close < level_px:
                wick_pct = (c_high - level_px) / level_px * 100
                if wick_pct >= 0.04:
                    t_pre = prev_c["time"] if prev_c else (c_time - interval_sec)
                    res_sweep = _process_sweep_state(
                        sig_key=wick_sig_key,
                        default_id=f"live-fb-up-{int(level_px*100)}-{c_time}",
                        sweep_type="bearish_sweep",
                        sub_type="wick_rejection",
                        level_px=level_px,
                        sweep_px=c_high,
                        direction="SHORT",
                        breakout_time=c_time,
                        conf_time=c_time,
                        base_form_title="Хибний пробій опору",
                        action_desc=f"Хибний пробій опору {level_px:.2f}: прокол до {c_high:.2f} та повернення під рівень",
                        t_pre=t_pre,
                    )
                    if res_sweep:
                        self._prev_candles[(coin, interval)] = candle
                        return res_sweep

            # Case B: Two-candle false breakout: prev closed above, current candle returns below
            if prev_c and prev_c["time"] < c_time:
                if prev_c["close"] >= level_px and c_close < level_px:
                    max_h = max(c_high, prev_c["high"])
                    res_sweep = _process_sweep_state(
                        sig_key=c2_sig_key,
                        default_id=f"live-fb-up-2c-{int(level_px*100)}-{c_time}",
                        sweep_type="bearish_sweep",
                        sub_type="two_candle_reversal",
                        level_px=level_px,
                        sweep_px=max_h,
                        direction="SHORT",
                        breakout_time=prev_c["time"],
                        conf_time=c_time,
                        base_form_title="Хибний пробій опору (2 свічки)",
                        action_desc=f"Хибний пробій опору {level_px:.2f}: вихід тілом свічки та повернення під рівень",
                        t_pre=prev_c["time"],
                    )
                    if res_sweep:
                        self._prev_candles[(coin, interval)] = candle
                        return res_sweep

        # 2. Check support false breakout / sweeps (Bullish Sweeps -> Long)
        for s in supports:
            level_px = s.get("center_price", s.get("price"))
            if not level_px:
                continue

            wick_sig_key = f"{coin}-{interval}-{c_time}-bullish-wick-{level_px}"
            c2_sig_key = f"{coin}-{interval}-{c_time}-bullish-2c-{level_px}"
            if not candle_is_closed and c_close <= level_px:
                if wick_sig_key in self._seen_live_sweeps and self._seen_live_sweeps[wick_sig_key].get("status") == "POTENTIAL":
                    self._seen_live_sweeps.pop(wick_sig_key, None)
                if c2_sig_key in self._seen_live_sweeps and self._seen_live_sweeps[c2_sig_key].get("status") == "POTENTIAL":
                    self._seen_live_sweeps.pop(c2_sig_key, None)

            # Case A: Pierced below level, currently above level
            if c_low < level_px and c_close > level_px:
                wick_pct = (level_px - c_low) / level_px * 100
                if wick_pct >= 0.04:
                    t_pre = prev_c["time"] if prev_c else (c_time - interval_sec)
                    res_sweep = _process_sweep_state(
                        sig_key=wick_sig_key,
                        default_id=f"live-fb-down-{int(level_px*100)}-{c_time}",
                        sweep_type="bullish_sweep",
                        sub_type="wick_rejection",
                        level_px=level_px,
                        sweep_px=c_low,
                        direction="LONG",
                        breakout_time=c_time,
                        conf_time=c_time,
                        base_form_title="Хибний пробій підтримки",
                        action_desc=f"Хибний пробій підтримки {level_px:.2f}: прокол до {c_low:.2f} та швидкий відкуп",
                        t_pre=t_pre,
                    )
                    if res_sweep:
                        self._prev_candles[(coin, interval)] = candle
                        return res_sweep

            # Case B: Two-candle false breakout: prev closed below, current candle returns above
            if prev_c and prev_c["time"] < c_time:
                if prev_c["close"] <= level_px and c_close > level_px:
                    min_l = min(c_low, prev_c["low"])
                    res_sweep = _process_sweep_state(
                        sig_key=c2_sig_key,
                        default_id=f"live-fb-down-2c-{int(level_px*100)}-{c_time}",
                        sweep_type="bullish_sweep",
                        sub_type="two_candle_reversal",
                        level_px=level_px,
                        sweep_px=min_l,
                        direction="LONG",
                        breakout_time=prev_c["time"],
                        conf_time=c_time,
                        base_form_title="Хибний пробій підтримки (2 свічки)",
                        action_desc=f"Хибний пробій підтримки {level_px:.2f}: вихід тілом свічки та повернення вище рівня",
                        t_pre=prev_c["time"],
                    )
                    if res_sweep:
                        self._prev_candles[(coin, interval)] = candle
                        return res_sweep

        # Keep current candle for future comparison when next candle arrives
        self._prev_candles[(coin, interval)] = candle
        return None

        # Keep current candle for future comparison when next candle arrives
        self._prev_candles[(coin, interval)] = candle
        return None


hl_ws_manager = HyperliquidWSManager()
