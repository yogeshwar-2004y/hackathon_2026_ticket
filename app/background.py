import threading
import queue
import time
import logging
from typing import Optional

from .classifier import keyword_classify, model_classify
from .queue_manager import queue_manager
from .notifications import notify_console, notify_slack

logger = logging.getLogger(__name__)

class BackgroundService:
    def __init__(self):
        self._task_q: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        # fake slack webhook (change to real URL to test)
        self.slack_webhook = "https://example.com/fake-slack-webhook"

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
        while self._running:
            try:
                ticket = self._task_q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._process(ticket)
            except Exception as e:
                logger.exception("Background processing failed: %s", e)
            finally:
                self._task_q.task_done()

    def _process(self, ticket):
        # Log old (keyword) classification for comparison
        old_cat, old_urg = keyword_classify(ticket.subject, ticket.body)
        logger.info("Ticket %s - keyword classification: %s (urgency=%.2f)", ticket.id, old_cat, old_urg)

        # Model-based classification
        model_cat, model_conf, model_urg = model_classify(ticket.subject, ticket.body)

        # Populate ticket fields
        ticket.metadata["keyword"] = {"category": old_cat, "urgency": old_urg}
        ticket.metadata["model"] = {"category": model_cat, "confidence": model_conf, "urgency": model_urg}
        ticket.category = model_cat
        ticket.urgency = model_urg
        ticket.status = "queued"

        # If high urgency, notify
        if ticket.urgency >= 0.80:
            msg = f"High urgency ticket {ticket.id}: {ticket.subject} (urgency={ticket.urgency:.2f})"
            notify_console(msg)
            notify_slack(self.slack_webhook, msg)

        # finally add to priority queue
        queue_manager.push(ticket)
        logger.info("Ticket %s pushed to priority queue (urgency=%.2f)", ticket.id, ticket.urgency)

background_service = BackgroundService()

