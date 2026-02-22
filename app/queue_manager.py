import os
import time
from typing import Any, Dict, List, Optional

import redis
from pymongo import MongoClient, ASCENDING, DESCENDING

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
PRIORITY_SET = "priority_queue"
INCOMING_LIST = "incoming_tasks"


class QueueManager:
    """
    Redis + Mongo-backed queue manager.
    """

    def __init__(self, redis_url: str = REDIS_URL, mongo_uri: str = MONGO_URI):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.mongo = MongoClient(mongo_uri)
        self.db = self.mongo["ticket_router"]
        self.tickets = self.db["tickets"]
        # ensure indexes
        try:
            self.tickets.create_index([("created_at", ASCENDING)])
            self.tickets.create_index([("urgency", DESCENDING)])
        except Exception:
            # ignore index errors (e.g., when Mongo not available at import time)
            pass

    def enqueue_ticket(self, ticket: Any) -> None:
        doc = {
            "_id": ticket.id,
            "id": ticket.id,
            "subject": ticket.subject,
            "body": ticket.body,
            "customer": ticket.customer,
            "category": ticket.category,
            "urgency": float(ticket.urgency or 0.0),
            "status": "received",
            "metadata": ticket.metadata or {},
            "created_at": ticket.created_at,
        }
        self.tickets.replace_one({"_id": ticket.id}, doc, upsert=True)
        self.redis.rpush(INCOMING_LIST, ticket.id)

    def push_priority(self, ticket_id: str, urgency: float) -> None:
        self.redis.zadd(PRIORITY_SET, {ticket_id: float(urgency)})
        try:
            self.tickets.update_one({"_id": ticket_id}, {"$set": {"urgency": float(urgency), "status": "queued"}})
        except Exception:
            pass

    def pop_priority(self) -> Optional[Dict[str, Any]]:
        res = self.redis.zpopmax(PRIORITY_SET, 1)
        if not res:
            return None
        ticket_id, score = res[0]
        doc = self.tickets.find_one({"_id": ticket_id})
        return doc

    def peek_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        ids = self.redis.zrevrange(PRIORITY_SET, 0, limit - 1)
        if not ids:
            return []
        docs = list(self.tickets.find({"_id": {"$in": ids}}))
        id_to_doc = {d["_id"]: d for d in docs}
        ordered = [id_to_doc.get(i) for i in ids if i in id_to_doc]
        results = []
        for d in ordered:
            results.append(
                {
                    "id": d.get("id"),
                    "subject": d.get("subject"),
                    "body": d.get("body"),
                    "customer": d.get("customer"),
                    "category": d.get("category"),
                    "urgency": d.get("urgency", 0.0),
                    "status": d.get("status"),
                    "metadata": d.get("metadata", {}),
                    "created_at": d.get("created_at"),
                }
            )
        return results


queue_manager = QueueManager()

