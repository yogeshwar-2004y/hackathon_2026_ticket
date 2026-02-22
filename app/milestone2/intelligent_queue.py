"""
Helpers for priority queues (Milestone 2).

Provides queue names and utility functions to map continuous urgency scores
to discrete labels ("high", "medium", "low") and push a ticket id to the
corresponding Redis list.
"""
from __future__ import annotations

from typing import Tuple
import os
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
HIGH_QUEUE = "high_priority_queue"
MEDIUM_QUEUE = "medium_priority_queue"
LOW_QUEUE = "low_priority_queue"
INCOMING = "incoming_tasks"


def score_to_label(score: float) -> str:
    """Map a numeric score in [0,1] to 'high'|'medium'|'low'."""
    try:
        s = float(score)
    except Exception:
        return "low"
    if s >= 0.8:
        return "high"
    if s >= 0.4:
        return "medium"
    return "low"


def push_to_priority(redis_conn: redis.Redis, ticket_id: str, urgency_label: str) -> None:
    """Push ticket_id to the correct Redis list (LPUSH)."""
    if urgency_label == "high":
        redis_conn.lpush(HIGH_QUEUE, ticket_id)
        print(f"Pushed ticket {ticket_id} -> {HIGH_QUEUE}")
    elif urgency_label == "medium":
        redis_conn.lpush(MEDIUM_QUEUE, ticket_id)
        print(f"Pushed ticket {ticket_id} -> {MEDIUM_QUEUE}")
    else:
        redis_conn.lpush(LOW_QUEUE, ticket_id)
        print(f"Pushed ticket {ticket_id} -> {LOW_QUEUE}")

