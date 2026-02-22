import threading
import queue
import time
import os
import logging
from typing import Optional

from .classifier import keyword_classify, model_classify
from .queue_manager import queue_manager
from .notifications import notify_console, notify_slack
from .circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)

class BackgroundService:
    def __init__(self):
        self._task_q: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        # fake slack webhook (change to real URL to test)
        self.slack_webhook = "https://example.com/fake-slack-webhook"
        # circuit breaker protecting ML inference (shared instance)
        self.circuit_breaker = get_circuit_breaker()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("BackgroundService started")

    def submit(self, ticket):
        """Quickly enqueue ticket for background processing."""
        self._task_q.put(ticket)
        logger.debug("Ticket %s submitted to background queue", ticket.id)

    def _worker(self):
        # Switch to Redis-backed incoming list consumption. This makes the worker
        # compatible with multiple processes and provides atomic dequeue semantics.
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        import redis as _redis

        r = _redis.from_url(redis_url, decode_responses=True)
        while self._running:
            try:
                # BRPOP blocks until an item is available (timeout to allow shutdown)
                item = r.brpop("incoming_tasks", timeout=2)
                if not item:
                    continue
                # item is tuple (list_name, ticket_id)
                _, ticket_id = item
                # fetch ticket from Mongo via queue_manager
                doc = queue_manager.tickets.find_one({"_id": ticket_id})
                if not doc:
                    logger.warning("Ticket %s not found in Mongo; skipping", ticket_id)
                    continue
                # convert doc to a simple Ticket-like object for processing
                from .models import Ticket

                ticket = Ticket(
                    id=doc.get("_id"),
                    subject=doc.get("subject", ""),
                    body=doc.get("body", ""),
                    customer=doc.get("customer", ""),
                )
                ticket.metadata = doc.get("metadata", {}) or {}
                ticket.status = doc.get("status", "received")
                ticket.urgency = float(doc.get("urgency", 0.0) or 0.0)
                ticket.created_at = doc.get("created_at", time.time())
                try:
                    self._process(ticket)
                except Exception as e:
                    logger.exception("Background processing failed: %s", e)
            except Exception as e:
                # Top-level loop error; log and continue
                logger.exception("Worker loop error: %s", e)

    def _process(self, ticket):
        # Log old (keyword) classification for comparison
        old_cat, old_urg = keyword_classify(ticket.subject, ticket.body)
        logger.info("Ticket %s - keyword classification: %s (urgency=%.2f)", ticket.id, old_cat, old_urg)
        # Store keyword metadata
        ticket.metadata["keyword"] = {"category": old_cat, "urgency": old_urg}

        # Define wrappers for the circuit breaker. We use a single model call
        # inside classify_wrapper and cache the result on the ticket so we don't
        # call the heavy model twice.
        def classify_wrapper(tkt):
            # call the model once and cache
            try:
                label, conf, urg = model_classify(tkt.subject, tkt.body)
                tkt.metadata["_model_cached"] = {"label": label, "confidence": conf, "urgency": urg}
                return label
            except Exception:
                # Let the breaker treat exceptions as failures
                raise

        def urgency_wrapper(tkt):
            cached = tkt.metadata.get("_model_cached")
            if cached:
                return float(cached.get("urgency", 0.0))
            # fallback: call model_classify (rare) and cache
            label, conf, urg = model_classify(tkt.subject, tkt.body)
            tkt.metadata["_model_cached"] = {"label": label, "confidence": conf, "urgency": urg}
            return float(urg)

        # Execute model calls under circuit protection.
        try:
            model_cat, model_urg = self.circuit_breaker.execute(classify_wrapper, urgency_wrapper, ticket)
        except Exception as e:
            # If breaker wrappers raise, fallback to keyword
            logger.exception("Circuit breaker execution failed: %s", e)
            model_cat, model_urg = old_cat, old_urg

        # Retrieve cached confidence if available
        cached = ticket.metadata.get("_model_cached", {})
        model_conf = cached.get("confidence")

        # Populate ticket fields with chosen values
        ticket.metadata["model"] = {"category": model_cat, "confidence": model_conf, "urgency": model_urg}
        ticket.category = model_cat
        ticket.urgency = model_urg
        ticket.status = "queued"

        # If high urgency, notify
        if ticket.urgency >= 0.80:
            msg = f"High urgency ticket {ticket.id}: {ticket.subject} (urgency={ticket.urgency:.2f})"
            notify_console(msg)
            notify_slack(self.slack_webhook, msg)

        # finally add to priority queue (Redis sorted set) and update Mongo
        try:
            queue_manager.push_priority(ticket.id, ticket.urgency)
            logger.info("Ticket %s pushed to priority queue (urgency=%.2f)", ticket.id, ticket.urgency)
        except Exception as e:
            logger.exception("Failed to push ticket %s to priority queue: %s", ticket.id, e)

background_service = BackgroundService()

