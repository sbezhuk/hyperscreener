import asyncio
import json
import logging
import time
from typing import Dict, Set, Any, Optional, Tuple, List
import websockets
from fastapi import WebSocket

from .hyperliquid import hl_client

logger = logging.getLogger("hyperscreener.ws")
logging.basicConfig(level=logging.INFO)

HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"


class HyperliquidWSManager:
    """
    Direct WebSocket connection manager for Hyperliquid (wss://api.hyperliquid.xyz/ws)
    Features:
    - Point 1.1: Direct streaming of candle and allMids real-time tick data.
    - Point 1.2: Automatic reconnection manager with exponential backoff & ping keepalive.
    - Point 1.3: Real-time on-the-fly sweep detection when candle touches/pierces levels.
    """

    def __init__(self):
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._hl_ws = None

        # Frontend client connections
        self._active_clients: Set[WebSocket] = set()
        # client -> set of (coin, interval)
        self._client_subs: Dict[WebSocket, Set[Tuple[str, str]]] = {}

        # Active subscriptions on Hyperliquid WS: set of (coin, interval)
        self._subscribed_topics: Set[Tuple[str, str]] = set()

        # Levels cache for live sweep checking: (coin, interval) -> { "resistances": [...], "supports": [...] }
        self._levels_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Avoid duplicate sweep notifications for identical (level, candle_time, direction)
        self._seen_live_sweeps: Set[str] = set()

        # Backoff parameters
        self._min_backoff = 1.0
        self._max_backoff = 16.0
        self._current_backoff = 1.0
        self.is_connected = False

    async def start(self):
        """Starts background task to manage Hyperliquid WS connection."""
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._connection_loop())

    async def stop(self):
        """Stops background tasks and closes connection."""
        self._running = False
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        if self._hl_ws:
            try:
                await self._hl_ws.close()
            except Exception:
                pass
        self._hl_ws = None
        self.is_connected = False

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

        # If not subscribed to Hyperliquid yet, subscribe now
        await self._ensure_hl_subscribed(coin, clean_tf)

    async def unsubscribe_client(self, client: WebSocket, coin: str, interval: str):
        coin = coin.upper()
        clean_tf = interval.lower()
        topic = (coin, clean_tf)
        if client in self._client_subs and topic in self._client_subs[client]:
            self._client_subs[client].remove(topic)
            await self._check_and_unsubscribe_if_unused(coin, clean_tf)

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
        """Continuously maintains connection to Hyperliquid WS with exponential backoff."""
        while self._running:
            try:
                logger.info(f"Connecting to Hyperliquid WebSocket: {HYPERLIQUID_WS_URL} ...")
                async with websockets.connect(
                    HYPERLIQUID_WS_URL,
                    ping_interval=None, # we manage custom ping
                    close_timeout=5,
                    max_size=10_000_000
                ) as ws:
                    self._hl_ws = ws
                    self.is_connected = True
                    self._current_backoff = self._min_backoff
                    logger.info("✅ Connected to Hyperliquid WebSocket successfully!")

                    # Broadcast connected status to clients
                    await self._broadcast_status("connected")

                    # Re-subscribe to all active topics
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

                    # Start ping keepalive
                    if self._ping_task and not self._ping_task.done():
                        self._ping_task.cancel()
                    self._ping_task = asyncio.create_task(self._ping_loop(ws))

                    # Receive messages
                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._handle_hl_message(raw_msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.is_connected = False
                self._hl_ws = None
                await self._broadcast_status("reconnecting")
                logger.warning(
                    f"⚠️ Hyperliquid WS disconnected ({e}). Reconnecting in {self._current_backoff:.1f}s..."
                )
                await asyncio.sleep(self._current_backoff)
                self._current_backoff = min(self._current_backoff * 2, self._max_backoff)

        self.is_connected = False
        self._hl_ws = None

    async def _ping_loop(self, ws):
        """Sends Hyperliquid ping every 30 seconds to keep connection fresh."""
        try:
            while self._running and self.is_connected:
                await asyncio.sleep(30)
                await ws.send(json.dumps({"method": "ping"}))
        except (asyncio.CancelledError, Exception):
            pass

    async def _broadcast_status(self, status: str):
        msg = json.dumps({"type": "ws_status", "status": status, "timestamp": time.time()})
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

    def _detect_live_sweep(self, coin: str, interval: str, candle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Instantaneous sweep detection against active levels.
        Triggers when candle's high/low pierces a level and closes back on the other side.
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

        # Check resistance sweeps (Bearish Sweeps -> Short)
        for r in resistances:
            level_px = r.get("price")
            if not level_px:
                continue

            # Pierced above level, but closed back below it!
            if c_high > level_px and c_close < level_px:
                wick_pct = (c_high - level_px) / level_px * 100
                if wick_pct >= 0.04:
                    sweep_sig = f"{coin}-{interval}-{c_time}-bearish-{level_px}"
                    if sweep_sig not in self._seen_live_sweeps:
                        self._seen_live_sweeps.add(sweep_sig)
                        return {
                            "type": "bearish_sweep",
                            "formation": "Хибний пробій опору (LIVE)",
                            "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                            "sweepPrice": round(c_high, 2 if c_high > 10 else 4),
                            "direction": "SHORT",
                            "time": c_time,
                            "desc": f"Миттєвий хибний пробій опору {level_px:.2f}: прокол до {c_high:.2f} та повернення під рівень",
                            "isLive": True
                        }

        # Check support sweeps (Bullish Sweeps -> Long)
        for s in supports:
            level_px = s.get("price")
            if not level_px:
                continue

            # Pierced below level, but closed back above it!
            if c_low < level_px and c_close > level_px:
                wick_pct = (level_px - c_low) / level_px * 100
                if wick_pct >= 0.04:
                    sweep_sig = f"{coin}-{interval}-{c_time}-bullish-{level_px}"
                    if sweep_sig not in self._seen_live_sweeps:
                        self._seen_live_sweeps.add(sweep_sig)
                        return {
                            "type": "bullish_sweep",
                            "formation": "Хибний пробій підтримки (LIVE)",
                            "levelPrice": round(level_px, 2 if level_px > 10 else 4),
                            "sweepPrice": round(c_low, 2 if c_low > 10 else 4),
                            "direction": "LONG",
                            "time": c_time,
                            "desc": f"Миттєвий хибний пробій підтримки {level_px:.2f}: прокол до {c_low:.2f} та швидкий відкуп",
                            "isLive": True
                        }

        return None


hl_ws_manager = HyperliquidWSManager()
