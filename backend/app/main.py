import asyncio
import json
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

from .hyperliquid import hl_client
from .analyzer.screener import analyze_coin_data, scan_market

app = FastAPI(title="Hyperliquid Screener API", version="1.0.0")

# Enable CORS for local web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections
active_websockets: List[WebSocket] = []

@app.on_event("shutdown")
async def shutdown_event():
    await hl_client.close()

@app.get("/api/coins")
async def get_coins():
    """Returns all active perpetual coins on Hyperliquid sorted by 24h volume."""
    try:
        coins = await hl_client.get_meta_and_contexts()
        return {"success": True, "count": len(coins), "coins": coins}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/candles")
async def get_candles(
    coin: str = Query("ETH", description="Coin symbol"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(300, ge=50, le=1000)
):
    """Returns OHLCV candles formatted for TradingView Lightweight Charts."""
    try:
        candles = await hl_client.get_candles(coin=coin.upper(), interval=interval, limit=limit)
        return {"success": True, "coin": coin.upper(), "interval": interval, "candles": candles}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/analysis")
async def get_analysis(
    coin: str = Query("ETH", description="Coin symbol"),
    interval: str = Query("5m", description="Candle interval (1m, 5m, 15m, 1h, 4h, 1d)")
):
    """Full technical & SMC analysis (Levels, FVGs, Sweeps, Structure, Signals)."""
    try:
        data = await analyze_coin_data(coin=coin.upper(), interval=interval, limit=300)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            # Keep-alive or handle client messages
            msg = await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
