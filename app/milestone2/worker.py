"""
Milestone2 background worker.

This worker BRPOP's ticket ids from the 'incoming_tasks' Redis list, processes
each ticket (runs M1 baseline and tries M2 under circuit protection), updates
MongoDB with final results, and pushes the ticket id into the appropriate
priority Redis queue (high/medium/low).
"""
from __future__ import annotations

import os
import time
import traceback
from typing import Any

import redis
from pymongo import MongoClient

from ..classifier import keyword_classify, model_classify
from .circuit_breaker import CircuitBreaker
from .intelligent_queue import REDIS_URL, INCOMING, push_to_priority, score_to_label

# Configuration
REDIS_URL = os.getenv("REDIS_URL", REDIS_URL)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
BRPOP_TIMEOUT = 2  # seconds


def run_worker():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    mc = MongoClient(MONGO_URI)
    tickets_coll = mc["ticket_router"]["tickets"]

    cb = CircuitBreaker()  # shared breaker for this worker process

    print("Milestone2 worker started. Listening for incoming tasks...")
    while True:
        try:
            item = r.brpop(INCOMING, timeout=BRPOP_TIMEOUT)
            if not item:
                continue
            _, ticket_id = item
            print(f"Worker popped incoming ticket: {ticket_id}")

            doc = tickets_coll.find_one({"_id": ticket_id})
            if not doc:
                print(f"Ticket {ticket_id} not found in Mongo, skipping")
                continue

            subject = doc.get("subject", "")
            body = doc.get("body", "")

            # M1 baseline (always)
            m1_cat, m1_urg_score = keyword_classify(subject, body)
            m1_urg_label = score_to_label(m1_urg_score)
            print(f"Ticket {ticket_id} - M1: {m1_cat} ({m1_urg_label})")
            # append to ticket logs
            try:
                r.rpush(f"logs:{ticket_id}", f"[M1] {ticket_id} -> {m1_cat} (score={m1_urg_score:.2f}) -> label={m1_urg_label}")
            except Exception:
                pass

            # Prepare M2 callable for circuit breaker
            def m2_call():
                lab, conf, urg = model_classify(subject, body)
                # model_classify returns float urgency; return label + score
                return lab, float(urg)

            # Try M2 under circuit breaker protection (returns info dict)
            used_model, m2_cat, m2_urg_score, info = cb.execute(m2_call)
            if info and info.get("elapsed_ms", 0) > 0 and info.get("consecutive_failures", 0) >= 0:
                try:
                    r.rpush(f"logs:{ticket_id}", f"M2 slow/failure: {info.get('elapsed_ms'):.1f}ms (failures={info.get('consecutive_failures')})")
                except Exception:
                    pass
            if used_model:
                final_cat = m2_cat
                final_label = score_to_label(m2_urg_score)
                which = "M2"
                print(f"Ticket {ticket_id} - M2 used: {m2_cat} ({final_label})")
                try:
                    r.rpush(f"logs:{ticket_id}", f"[M2] Used for {ticket_id}: {m2_cat} (score={m2_urg_score:.2f})")
                except Exception:
                    pass
            else:
                final_cat = m1_cat
                final_label = m1_urg_label
                which = "M1"
                print(f"Ticket {ticket_id} - Using M1 fallback (circuit open or M2 slow)")
                try:
                    r.rpush(f"logs:{ticket_id}", f"[Fallback] Using M1 for {ticket_id}")
                except Exception:
                    pass

            # Update Mongo with final decision
            update = {
                "$set": {
                    "category": final_cat,
                    "urgency": final_label,
                    "status": "queued",
                    "processed_by": which,
                    "metadata.m1": {"category": m1_cat, "score": m1_urg_score},
                    "metadata.m2": {"category": m2_cat if used_model else None, "score": m2_urg_score if used_model else None},
                    "updated_at": time.time(),
                }
            }
            tickets_coll.update_one({"_id": ticket_id}, update)

            # Push into priority queue based on final_label
            push_to_priority(r, ticket_id, final_label)
            try:
                r.rpush(f"logs:{ticket_id}", f"Pushed ticket {ticket_id} -> {final_label}_priority_queue")
            except Exception:
                pass

        except Exception:
            print("Worker error:", traceback.format_exc())
            time.sleep(1)


if __name__ == "__main__":
    run_worker()

