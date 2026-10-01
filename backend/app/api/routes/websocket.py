"""
StockMind AI — WebSocket Routes
Real-time data streaming from backend to browser clients.
Upstox tokens stay server-side; browser receives normalized events.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.config import get_settings
from app.core.logging import get_logger
from app.core.security import decode_token

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, client_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self.active_connections[client_id] = ws
        logger.info("ws_client_connected", client_id=client_id, total=len(self.active_connections))

    async def disconnect(self, client_id: str) -> None:
        async with self._lock:
            self.active_connections.pop(client_id, None)
        logger.info("ws_client_disconnected", client_id=client_id, total=len(self.active_connections))

    async def send_to_client(self, client_id: str, message: dict) -> None:
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(client_id)

    async def broadcast(self, message: dict) -> None:
        disconnected = []
        for client_id, ws in self.active_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)
        for cid in disconnected:
            await self.disconnect(cid)

    @property
    def count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()


def _authenticate_ws(token: Optional[str]) -> Optional[str]:
    """Authenticate WebSocket connection via JWT token."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/market")
async def market_data_websocket(
    ws: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Real-time market data stream to browser clients.

    The server maintains the Upstox WebSocket connection.
    Browser clients subscribe to instruments via this endpoint.
    Upstox tokens NEVER leave the server.
    """
    user_id = _authenticate_ws(token)
    client_id = user_id or f"anon_{id(ws)}"

    await manager.connect(ws, client_id)

    try:
        while True:
            # Receive subscription messages from client
            data = await ws.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    instruments = message.get("instruments", [])
                    await ws.send_json({
                        "type": "subscription_ack",
                        "instruments": instruments,
                        "status": "subscribed",
                        "note": "Real-time data requires active Upstox connection",
                    })

                elif action == "unsubscribe":
                    instruments = message.get("instruments", [])
                    await ws.send_json({
                        "type": "unsubscription_ack",
                        "instruments": instruments,
                    })

                elif action == "ping":
                    await ws.send_json({"type": "pong"})

                else:
                    await ws.send_json({
                        "type": "error",
                        "message": f"Unknown action: {action}",
                    })

            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "error",
                    "message": "Invalid JSON message",
                })

    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error("ws_error", client_id=client_id, error=str(e))
        await manager.disconnect(client_id)
