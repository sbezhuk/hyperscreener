import asyncio
import json
import time
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import httpx

from .hyperliquid import hl_client
from .ws_manager import hl_ws_manager
from .analyzer.screener import analyze_coin_data, scan_market
from .analyzer.oi_tracker import oi_manager

app = FastAPI(title="Hyperliquid Screener API", version="1.0.0")

# Enable CORS for local web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Start direct Hyperliquid WebSocket manager in the background
    await hl_ws_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    await hl_ws_manager.stop()
    await hl_client.close()

@app.get("/api/coins")
async def get_coins():
    """Returns all active perpetual coins on Hyperliquid sorted by 24h volume."""
    try:
        coins = await hl_client.get_meta_and_contexts()
        return {"success": True, "count": len(coins), "coins": coins}
    except httpx.HTTPStatusError as e:
        status = 429 if e.response.status_code == 429 else 502
        return JSONResponse(status_code=status, content={"success": False, "error": f"Помилка Hyperliquid ({e.response.status_code}): {e.response.text or 'Недоступно'}"})
    except httpx.TimeoutException as e:
        return JSONResponse(status_code=504, content={"success": False, "error": f"Таймаут підключення до біржі Hyperliquid: {str(e)}"})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"success": False, "error": f"Мережева помилка зв'язку з біржею Hyperliquid: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"Помилка отримання списку монет: {str(e)}"})

@app.get("/api/candles")
async def get_candles(
    coin: str = Query("ETH", description="Coin symbol"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(500, ge=50, le=5000),
    before: Optional[int] = Query(None, description="Fetch candles before this unix timestamp in seconds (for lazy pagination)")
):
    """Returns OHLCV candles formatted for TradingView Lightweight Charts with pagination support."""
    try:
        end_time_ms = (before * 1000) if before else None
        candles = await hl_client.get_candles(
            coin=coin.upper(),
            interval=interval,
            limit=limit,
            end_time=end_time_ms
        )
        if not candles:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": f"Свічки для монети '{coin.upper()}' ({interval}) не знайдено на біржі.",
                    "coin": coin.upper(),
                    "interval": interval,
                    "candles": []
                }
            )
        return {"success": True, "coin": coin.upper(), "interval": interval, "candles": candles}
    except httpx.HTTPStatusError as e:
        status = 429 if e.response.status_code == 429 else 502
        return JSONResponse(status_code=status, content={"success": False, "error": f"Помилка біржі Hyperliquid ({e.response.status_code})", "coin": coin.upper(), "interval": interval, "candles": []})
    except httpx.TimeoutException as e:
        return JSONResponse(status_code=504, content={"success": False, "error": f"Таймаут з'єднання з Hyperliquid: {str(e)}", "coin": coin.upper(), "interval": interval, "candles": []})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"success": False, "error": f"Мережева помилка зв'язку з біржею Hyperliquid: {str(e)}", "coin": coin.upper(), "interval": interval, "candles": []})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"Помилка завантаження свічок {coin.upper()}: {str(e)}", "coin": coin.upper(), "interval": interval, "candles": []})

@app.get("/api/analysis")
async def get_analysis(
    coin: str = Query("ETH", description="Coin symbol"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(600, ge=50, le=2000)
):
    """Full technical & SMC analysis (Levels, FVGs, Sweeps, Structure, Signals)."""
    try:
        data = await analyze_coin_data(coin=coin.upper(), interval=interval, limit=limit)
        if not data or not data.get("candles"):
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Історичні свічки для монети '{coin.upper()}' ({interval}) відсутні або монету не знайдено."}
            )
        return {"success": True, "data": data}
    except httpx.HTTPStatusError as e:
        status = 429 if e.response.status_code == 429 else 502
        return JSONResponse(status_code=status, content={"success": False, "error": f"Помилка зовнішнього API біржі Hyperliquid ({e.response.status_code})"})
    except httpx.TimeoutException as e:
        return JSONResponse(status_code=504, content={"success": False, "error": f"Таймаут підключення до сервера Hyperliquid: {str(e)}"})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"success": False, "error": f"Мережева помилка зв'язку з сервером Hyperliquid: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"Помилка сервера при аналізі {coin.upper()}: {str(e)}"})

@app.get("/api/screener")
async def get_screener_signals(
    top_n: int = Query(25, ge=5, le=50),
    interval: str = Query("5m")
):
    """Scans top N coins on Hyperliquid for actionable trading formations."""
    try:
        results = await scan_market(top_n=top_n, interval=interval)
        return {"success": True, "count": len(results), "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/oi")
async def get_oi(coin: str = Query("ETH", description="Coin symbol")):
    """Returns real-time Open Interest, 1m/5m/15m/1h deltas, volatility thresholds and level interpretations."""
    try:
        coin_upper = coin.upper()
        tracker = oi_manager.get_tracker(coin_upper)
        if not tracker._history:
            meta = await hl_client.get_meta_and_contexts()
            for c in meta:
                if c["name"] == coin_upper:
                    oi_manager.record_tick(coin_upper, c["openInterest"], c["markPrice"])
                    break

        levels = hl_ws_manager._get_all_levels_for_coin(coin_upper)
        summary = oi_manager.get_coin_oi_summary(coin_upper, levels=levels)
        return {"success": True, "data": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/ws/status")
async def get_ws_status():
    """Returns current exchange WebSocket connection state, diagnostics, and active topics."""
    return {
        "success": True,
        "state": hl_ws_manager.state.value,
        "is_connected": hl_ws_manager.is_connected,
        "diagnostics": hl_ws_manager.reconnect_mgr.get_diagnostics(),
        "subscribed_topics": [
            {"coin": coin, "interval": interval}
            for coin, interval in hl_ws_manager._subscribed_topics
        ],
        "monitored_oi_coins_count": len(hl_ws_manager._monitored_oi_coins),
        "active_clients_count": len(hl_ws_manager._active_clients)
    }

@app.post("/api/ws/disconnect")
async def manual_ws_disconnect():
    """Manually disconnects exchange WebSocket and halts auto-reconnection."""
    await hl_ws_manager.manual_disconnect()
    return {
        "success": True,
        "message": "Manual disconnect initiated. Auto-reconnection paused.",
        "state": hl_ws_manager.state.value
    }

@app.post("/api/ws/reconnect")
async def manual_ws_reconnect():
    """Manually reconnects exchange WebSocket and resumes auto-reconnection with reset backoff."""
    await hl_ws_manager.manual_reconnect()
    return {
        "success": True,
        "message": "Manual reconnect initiated.",
        "state": hl_ws_manager.state.value
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await hl_ws_manager.register_client(websocket)
    try:
        # Send initial status with full diagnostics
        await websocket.send_json({
            "type": "ws_status",
            "status": hl_ws_manager.state.value,
            "timestamp": time.time(),
            "diagnostics": hl_ws_manager.reconnect_mgr.get_diagnostics()
        })

        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
            except Exception:
                continue

            action = msg.get("action") or msg.get("type")
            coin = msg.get("coin", "ETH")
            interval = msg.get("interval", "1d")

            if action in ["subscribe", "sub"]:
                await hl_ws_manager.subscribe_client(websocket, coin, interval)
                await websocket.send_json({
                    "type": "subscribed",
                    "coin": coin.upper(),
                    "interval": interval.lower()
                })
            elif action in ["unsubscribe", "unsub"]:
                await hl_ws_manager.unsubscribe_client(websocket, coin, interval)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "coin": coin.upper(),
                    "interval": interval.lower()
                })
            elif action == "disconnect":
                await hl_ws_manager.manual_disconnect()
                await websocket.send_json({
                    "type": "ws_status",
                    "status": hl_ws_manager.state.value,
                    "is_manual": True
                })
            elif action == "reconnect":
                await hl_ws_manager.manual_reconnect()
                await websocket.send_json({
                    "type": "ws_status",
                    "status": hl_ws_manager.state.value,
                    "is_manual": False
                })
            elif action == "status":
                await websocket.send_json({
                    "type": "ws_status",
                    "status": hl_ws_manager.state.value,
                    "diagnostics": hl_ws_manager.reconnect_mgr.get_diagnostics()
                })
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await hl_ws_manager.unregister_client(websocket)
    except Exception:
        await hl_ws_manager.unregister_client(websocket)
