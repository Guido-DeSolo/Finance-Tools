"""Alpaca Trading API order-update stream with reconnect support."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

OrderUpdate = Callable[[dict[str, Any]], None]
StatusUpdate = Callable[[str], None]


def decode_message(message: str | bytes) -> dict[str, Any]:
    """Decode Alpaca text or binary JSON frames."""
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = json.loads(message)
    return payload if isinstance(payload, dict) else {}


def merge_order(orders: list[dict[str, Any]], order: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    """Replace an order by ID, or insert a newly observed order, newest first."""
    order_id = order.get("id")
    if not order_id:
        return list(orders)
    merged = [dict(order)]
    merged.extend(item for item in orders if item.get("id") != order_id)
    merged.sort(key=lambda item: item.get("submitted_at") or "", reverse=True)
    return merged[:limit]


def reconcile_orders(rest_orders: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine a REST snapshot with stream state without regressing newer events."""
    by_id = {item.get("id"): dict(item) for item in rest_orders if item.get("id")}
    for item in current:
        order_id = item.get("id")
        rest = by_id.get(order_id)
        if order_id and (rest is None or (item.get("updated_at") or "") > (rest.get("updated_at") or "")):
            by_id[order_id] = dict(item)
    result = list(by_id.values())
    result.sort(key=lambda item: item.get("submitted_at") or "", reverse=True)
    return result[:50]


def authentication_message(key_id: str, secret_key: str) -> str:
    """Build the Trading API stream's documented authentication message."""
    return json.dumps({"action": "auth", "key": key_id, "secret": secret_key})


class OrderUpdateStream:
    def __init__(self, key_id: str, secret_key: str, trading_base: str):
        self.key_id = key_id
        self.secret_key = secret_key
        self.url = f"{trading_base.rstrip('/')}/stream".replace("https://", "wss://", 1)

    def run(self, stop: Any, on_update: OrderUpdate, on_status: StatusUpdate) -> None:
        asyncio.run(self._run(stop, on_update, on_status))

    async def _run(self, stop: Any, on_update: OrderUpdate, on_status: StatusUpdate) -> None:
        try:
            import websockets
        except ImportError:
            on_status("Order stream unavailable: install websockets")
            return

        delay = 1
        while not stop.is_set():
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as socket:
                    await socket.send(authentication_message(self.key_id, self.secret_key))
                    await socket.send(json.dumps({
                        "action": "listen", "data": {"streams": ["trade_updates"]},
                    }))
                    delay = 1
                    while not stop.is_set():
                        try:
                            message = await asyncio.wait_for(socket.recv(), timeout=1)
                        except TimeoutError:
                            continue
                        payload = decode_message(message)
                        stream = payload.get("stream")
                        data = payload.get("data") or {}
                        if stream == "listening" and "trade_updates" in data.get("streams", []):
                            on_status("Order stream connected")
                        elif stream == "authorization" and data.get("status") != "authorized":
                            raise RuntimeError("order stream authorization failed")
                        elif stream == "trade_updates" and isinstance(data.get("order"), dict):
                            on_update(data)
                        elif payload.get("action") == "error":
                            raise RuntimeError(data.get("error_message") or "order stream error")
            except Exception as error:
                if stop.is_set():
                    break
                on_status(f"Order stream reconnecting: {str(error)[:100]}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
