import uuid
import time
import os
import json
from flask import Flask, request, jsonify
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from transformers import pipeline
import redis
from .circuit_breaker import CircuitBreaker
from .intelligent_queue import REDIS_URL, INCOMING, push_to_priority, score_to_label

app = Flask(__name__)

# ML pipelines (M2)
classifier = pipeline("text-classification", model="distilbert-base-uncased")
sentiment_model = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

# Redis connection (stores ticket payloads and priority lists)
redis_conn = redis.from_url(os.getenv("REDIS_URL", REDIS_URL), decode_responses=True)

# Circuit breaker for protecting M2
cb = CircuitBreaker()


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


def map_category(label: str) -> str:
    label = label.lower()
    if "billing" in label:
        return "Billing"
    if "legal" in label:
        return "Legal"
    return "Technical"


def compute_urgency(text: str) -> float:
    result = sentiment_model(text)[0]
    score = result.get("score", 0.5)
    # map sentiment to a 0..1 urgency where negative sentiment -> higher urgency
    if result.get("label", "").upper() == "NEGATIVE":
        return float(score)
    return float(1.0 - score)


def keyword_classify(subject: str, body: str) -> (str, float):
    """Simple regex/keyword-based classifier returning (category, urgency_score[0..1])."""
    text = f"{subject}\n{body}".lower()
    if any(w in text for w in ["bill", "charge", "invoice", "refund"]):
        cat = "Billing"
    elif any(w in text for w in ["contract", "law", "privacy", "terms"]):
        cat = "Legal"
    else:
        cat = "Technical"

    urgency = 0.0
    if any(x in text for x in ["urgent", "asap", "immediately"]):
        urgency += 0.6
    if "!!" in text or "!!!" in text:
        urgency += 0.2
    if any(x in text for x in ["down", "broken", "not working", "error", "fail"]):
        urgency += 0.3
    urgency = max(0.0, min(1.0, urgency))
    return cat, urgency


@app.route("/submit", methods=["POST"])
def submit_ticket():
    """
    Accept ticket JSON, run M1 baseline, attempt M2 under CircuitBreaker,
    persist ticket payload to Redis, and push ticket id to the correct
    priority queue (high/medium/low).
    """
    data = request.get_json(force=True)
    ticket_id = str(uuid.uuid4())

    subject = data.get("subject", "")[:2000]
    body = data.get("body", "")[:10000]
    customer = data.get("customer", "unknown")

    # M1 baseline
    m1_cat, m1_score = keyword_classify(subject, body)
    m1_label = score_to_label(m1_score)
    print(f"[M1] {ticket_id} -> {m1_cat} (score={m1_score:.2f}) -> label={m1_label}")

    # Prepare M2 callable for the breaker
    def m2_callable():
        full = subject + " " + body
        pred = classifier(full)[0]
        m2_cat = map_category(pred.get("label", ""))
        m2_score = compute_urgency(full)
        return m2_cat, float(m2_score)

    used_model, m2_cat, m2_score, info = cb.execute(m2_callable)
    # record potential slow/failure info
    if info and info.get("elapsed_ms", 0) > 0:
        try:
            redis_conn.rpush(f"logs:{ticket_id}", f"M2 slow/failure: {info.get('elapsed_ms'):.1f}ms (failures={info.get('consecutive_failures')})")
        except Exception:
            pass

    if used_model:
        final_cat = m2_cat
        final_score = m2_score
        used = "M2"
        print(f"[M2] Used for {ticket_id}: {final_cat} (score={final_score:.2f})")
    else:
        final_cat = m1_cat
        final_score = m1_score
        used = "M1"
        print(f"[Fallback] Using M1 for {ticket_id}")

    final_label = score_to_label(final_score)

    # Persist ticket payload in Redis (simple JSON) and push to priority queue
    payload = {
        "id": ticket_id,
        "subject": subject,
        "body": body,
        "customer": customer,
        "category": final_cat,
        "urgency_score": final_score,
        "urgency_label": final_label,
        "processed_by": used,
        "created_at": time.time(),
    }
    redis_conn.set(f"ticket:{ticket_id}", json.dumps(payload))
    # initialize logs list and add initial entries
    log_key = f"logs:{ticket_id}"
    try:
        redis_conn.delete(log_key)
        redis_conn.rpush(log_key, f"[M1] {ticket_id} -> {m1_cat} (score={m1_score:.2f}) -> label={m1_label}")
        if used == "M2":
            redis_conn.rpush(log_key, f"[M2] Used for {ticket_id}: {final_cat} (score={final_score:.2f})")
        else:
            redis_conn.rpush(log_key, f"[Fallback] Using M1 for {ticket_id}")
        redis_conn.rpush(log_key, f"Pushed ticket {ticket_id} -> {final_label}_priority_queue")
    except Exception:
        pass
    # push to corresponding priority list
    push_to_priority(redis_conn, ticket_id, final_label)

    return jsonify({"ticket_id": ticket_id, "category": final_cat, "urgency": final_label, "processed_by": used}), 202

@app.route("/next", methods=["GET"])
def next_ticket():
    """
    Pop next ticket from priority queues (high -> medium -> low) and return
    stored payload from Redis. Uses RPOP since we LPUSH when enqueuing.
    """
    # try high, then medium, then low
    for q in ("high_priority_queue", "medium_priority_queue", "low_priority_queue"):
        ticket_id = redis_conn.rpop(q)
        if ticket_id:
            payload_json = redis_conn.get(f"ticket:{ticket_id}")
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except Exception:
                payload = {"id": ticket_id}
            return jsonify({"queue": q, "ticket": payload})
    return jsonify({"message": "No tickets available"})


@app.route("/ticket_logs/<ticket_id>", methods=["GET"])
def get_ticket_logs(ticket_id):
    """Return processing log lines for a ticket (from Redis list)."""
    key = f"logs:{ticket_id}"
    try:
        lines = redis_conn.lrange(key, 0, -1)
    except Exception:
        lines = []
    return jsonify({"ticket_id": ticket_id, "logs": lines})

# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, threaded=True)