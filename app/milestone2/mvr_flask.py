"""
Minimal Flask API for Milestone 2 (M2) — accepts tickets and enqueues for processing.

POST /tickets
  - accepts JSON { subject, body, customer }
  - stores ticket in MongoDB with status="received"
  - LPUSH ticket id to Redis "incoming_tasks"
  - returns 202 Accepted
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict

from flask import Flask, request, jsonify
import redis
from pymongo import MongoClient

from ..classifier import keyword_classify
from .intelligent_queue import REDIS_URL, INCOMING

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
REDIS_URL = os.getenv("REDIS_URL", REDIS_URL)

app = Flask(__name__)

# Connections (lazy)
_redis: redis.Redis | None = None
_mongo_client: MongoClient | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def get_mongo():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI)
    return _mongo_client


def ticket_doc_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    tid = str(uuid.uuid4())
    return {
        "_id": tid,
        "id": tid,
        "subject": payload.get("subject", "")[:2000],
        "body": payload.get("body", "")[:10000],
        "customer": payload.get("customer", "") or "unknown",
        "status": "received",
        "metadata": {},
        "created_at": time.time(),
    }


@app.route("/tickets", methods=["POST"])
def create_ticket():
    payload = request.get_json(force=True)
    if not payload:
        return jsonify({"error": "invalid payload"}), 400

    doc = ticket_doc_from_payload(payload)

    # persist to Mongo
    mc = get_mongo()
    tickets = mc["ticket_router"]["tickets"]
    tickets.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    # push to Redis incoming list
    r = get_redis()
    r.lpush(INCOMING, doc["_id"])
    print(f"Enqueued ticket {doc['_id']} -> {INCOMING}")

    return jsonify({"ticket_id": doc["_id"], "status": "accepted"}), 202


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

import re
import uuid
import heapq
import time
import numpy as np
from flask import Flask, request, jsonify
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from threading import Lock
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF

app = Flask(__name__)

# -----------------------------
# Database Model
# -----------------------------
@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    customer: str
    category: Optional[str] = None
    urgency: float = 0.0
    status: str = "new"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())

# -----------------------------
# In-memory storage
# -----------------------------
ticket_queue: List = []
queue_lock = Lock()

# -----------------------------
# Global ML Components
# -----------------------------
documents: List[str] = []

vectorizer = TfidfVectorizer(
    stop_words='english',
    max_df=0.95,   # Ignore terms in >95% documents
    min_df=2       # Ignore rare terms (<2 documents)
)

nmf_model = NMF(
    n_components=3,  # Billing, Technical, Legal
    random_state=42
)

fitted = False

# -----------------------------
# Train NMF Model
# -----------------------------
def train_nmf():
    global fitted

    if len(documents) < 3:
        return

    tfidf = vectorizer.fit_transform(documents)
    nmf_model.fit(tfidf)
    fitted = True

# -----------------------------
# Classify using NMF
# -----------------------------
def classify_ticket_nmf(text: str) -> str:
    if not fitted:
        return "Technical"  # fallback until enough data

    tfidf = vectorizer.transform([text])
    topic_distribution = nmf_model.transform(tfidf)

    topic_index = np.argmax(topic_distribution)

    topic_map = {
        0: "Billing",
        1: "Technical",
        2: "Legal"
    }

    return topic_map.get(topic_index, "Technical")

# -----------------------------
# Regex Urgency Heuristic
# -----------------------------
def compute_urgency(text: str) -> float:
    urgent_pattern = r"(asap|urgent|immediately|broken|critical)"
    if re.search(urgent_pattern, text.lower()):
        return 0.9
    return 0.3

# -----------------------------
# Routes
# -----------------------------
@app.route("/submit", methods=["POST"])
def submit_ticket():
    global documents

    data = request.json
    ticket_id = str(uuid.uuid4())

    full_text = data["subject"] + " " + data["body"]
    documents.append(full_text)

    train_nmf()

    category = classify_ticket_nmf(full_text)
    urgency = compute_urgency(full_text)

    ticket = Ticket(
        id=ticket_id,
        subject=data["subject"],
        body=data["body"],
        customer=data["customer"],
        category=category,
        urgency=urgency
    )

    with queue_lock:
        heapq.heappush(ticket_queue, (-urgency, ticket.created_at, ticket))

    return jsonify({
        "ticket_id": ticket.id,
        "category": ticket.category,
        "urgency": ticket.urgency
    })

@app.route("/next", methods=["GET"])
def next_ticket():
    with queue_lock:
        if not ticket_queue:
            return jsonify({"message": "No tickets available"})

        _, _, ticket = heapq.heappop(ticket_queue)
        ticket.status = "processing"

    return jsonify(ticket.__dict__)

# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, threaded=True)