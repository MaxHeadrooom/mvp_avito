"""Reference integration for one restaurant.

The service receives a webhook from Kitchen Core and exposes a tiny operator API.
It deliberately has no database: persistence is not needed to demonstrate the
contract, while the Core remains the source of truth for order state.
"""

import os
import threading
from dataclasses import asdict, dataclass

import httpx
from flask import Flask, jsonify, request

app = Flask(__name__)

CORE_BASE_URL = os.environ.get("CORE_BASE_URL", "http://kitchen-core:8000")
ESTABLISHMENT_ID = os.environ.get("ESTABLISHMENT_ID")


@dataclass(frozen=True)
class IncomingOrder:
    order_id: str
    establishment_id: str


_orders: dict[str, IncomingOrder] = {}
_lock = threading.Lock()


def _core_url(order_id: str, action: str) -> str:
    if not ESTABLISHMENT_ID:
        raise RuntimeError("ESTABLISHMENT_ID is not configured")
    return f"{CORE_BASE_URL}/establishments/{ESTABLISHMENT_ID}/orders/{order_id}/{action}"


@app.post("/notifications/orders")
def order_notification():
    payload = request.get_json(silent=True) or {}
    order_id = payload.get("order_id")
    establishment_id = payload.get("establishment_id")
    if not isinstance(order_id, str) or not isinstance(establishment_id, str):
        return jsonify({"detail": "order_id and establishment_id are required strings"}), 400
    if ESTABLISHMENT_ID and establishment_id != ESTABLISHMENT_ID:
        return jsonify({"detail": "notification belongs to another establishment"}), 409

    with _lock:
        is_new = order_id not in _orders
        _orders.setdefault(order_id, IncomingOrder(order_id, establishment_id))
    return jsonify({"status": "received" if is_new else "duplicate"}), 200


@app.get("/orders")
def list_incoming_orders():
    with _lock:
        orders = [asdict(order) for order in _orders.values()]
    return jsonify({"orders": orders})


@app.post("/orders/<order_id>/decision")
def decide_order(order_id: str):
    payload = request.get_json(silent=True) or {}
    accept = payload.get("accept")
    reason = payload.get("reason")
    if not isinstance(accept, bool):
        return jsonify({"detail": "accept must be a boolean"}), 400
    if not accept and not isinstance(reason, str):
        return jsonify({"detail": "reason is required when rejecting an order"}), 400
    response = httpx.post(
        _core_url(order_id, "decision"),
        json={"accept": accept, "reason": reason},
        timeout=5.0,
    )
    return jsonify(response.json()), response.status_code


@app.post("/orders/<order_id>/status")
def move_order_status(order_id: str):
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if not isinstance(status, str):
        return jsonify({"detail": "status must be a string"}), 400
    response = httpx.post(
        _core_url(order_id, "status"),
        json={"status": status, "comment": payload.get("comment")},
        timeout=5.0,
    )
    return jsonify(response.json()), response.status_code


@app.get("/health")
def health():
    return jsonify({"status": "ok", "establishment_id": ESTABLISHMENT_ID})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)

