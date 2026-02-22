import json
import os
import threading
import time
from typing import Set

import redis
from flask_sock import Sock

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
STATUS_CHANNEL = "ticket_status_events"

_redis = redis.from_url(REDIS_URL, decode_responses=True)
_clients_lock = threading.Lock()
_clients: Set[object] = set()
_subscriber_started = False


def _broadcast(raw_message: str) -> None:
    stale_clients = []
    with _clients_lock:
        clients = list(_clients)
    for ws in clients:
        try:
            ws.send(raw_message)
        except Exception:
            stale_clients.append(ws)
    if stale_clients:
        with _clients_lock:
            for ws in stale_clients:
                _clients.discard(ws)


def _status_subscriber() -> None:
    pubsub = _redis.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(STATUS_CHANNEL)
    for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        data = message.get("data")
        if isinstance(data, str):
            _broadcast(data)


def publish_status(ticket_id: str, status: str, **extra) -> None:
    payload = {"ticket_id": ticket_id, "status": status, "timestamp": time.time()}
    if extra:
        payload.update(extra)
    _redis.publish(STATUS_CHANNEL, json.dumps(payload, ensure_ascii=True))


def init_ws(app) -> None:
    global _subscriber_started
    sock = Sock(app)

    @sock.route("/ws/status")
    def ws_status(ws):
        with _clients_lock:
            _clients.add(ws)
        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break
        finally:
            with _clients_lock:
                _clients.discard(ws)

    if not _subscriber_started:
        t = threading.Thread(target=_status_subscriber, daemon=True)
        t.start()
        _subscriber_started = True
