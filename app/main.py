import os
import time
import uuid
from flask import current_app, Flask, request, jsonify, render_template
from flask_cors import CORS
from app.models import Ticket
from app.classifier import keyword_classify
from app.queue_manager import queue_manager
from app.background import background_service
from app.circuit_breaker import get_circuit_breaker
from app.milestone2 import intelligent_queue_flask as m2_intel
from app.milestone2 import worker as m2_worker

MODE = os.getenv("ROUTER_MODE", "m2").lower()

def create_app():
    # Tell Flask to look for templates/static inside the package
    app = Flask(__name__, template_folder="templates", static_folder="static")
    # Allow cross-origin requests from the frontend dev server (and others).
    # In production restrict origins appropriately.
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ensure background service initialized (only in m2)
    if MODE == "m2":
        background_service.start()
        # register milestone2 endpoints on the main app
        # use the functions defined in app.milestone2.intelligent_queue_flask
        app.add_url_rule("/submit", "submit_ticket", m2_intel.submit_ticket, methods=["POST"])
        app.add_url_rule("/next", "next_ticket", m2_intel.next_ticket, methods=["GET"])
        app.add_url_rule("/ticket_logs/<ticket_id>", "ticket_logs", m2_intel.get_ticket_logs, methods=["GET"])
        # start milestone2 worker in a daemon thread
        import threading

        def _start_m2_worker():
            try:
                m2_worker.run_worker()
            except Exception as e:
                # log and swallow to avoid crashing the main thread
                import logging

                logging.exception("Milestone2 worker failed: %s", e)

        t = threading.Thread(target=_start_m2_worker, daemon=True)
        t.start()

    @app.route("/", methods=["GET"])
    def index():
        # simple server-rendered UI for submitting tickets and viewing queue
        return render_template("index.html", mode=MODE)

    @app.route("/tickets", methods=["POST"])
    def create_ticket():
        payload = request.get_json(force=True)
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        customer = payload.get("customer", "")

        ticket_id = str(uuid.uuid4())
        ticket = Ticket(
            id=ticket_id,
            subject=subject,
            body=body,
            customer=customer,
        )

        # Milestone 1 synchronous keyword routing
        if MODE == "m1":
            category, urgency = keyword_classify(subject, body)
            ticket.category = category
            ticket.urgency = urgency
            ticket.status = "queued"
            # persist to Mongo and add to Redis priority set
            try:
                queue_manager.tickets.replace_one(
                    {"_id": ticket.id},
                    {
                        "_id": ticket.id,
                        "id": ticket.id,
                        "subject": ticket.subject,
                        "body": ticket.body,
                        "customer": ticket.customer,
                        "category": ticket.category,
                        "urgency": float(ticket.urgency),
                        "status": ticket.status,
                        "metadata": ticket.metadata,
                        "created_at": ticket.created_at,
                    },
                    upsert=True,
                )
                queue_manager.push_priority(ticket.id, ticket.urgency)
            except Exception:
                # best-effort: return the result even if persistence fails
                pass
            return (
                jsonify(
                    {"ticket_id": ticket.id, "category": ticket.category, "urgency": round(ticket.urgency, 2), "status": ticket.status}
                ),
                200,
            )

        # Milestone 2 async: accept quickly, process via Redis broker + Mongo
        else:
            # store minimal info and enqueue background processing via Redis + Mongo
            ticket.status = "received"
            queue_manager.enqueue_ticket(ticket)
            return jsonify({"ticket_id": ticket.id, "status": "accepted"}), 202

    @app.route("/queue", methods=["GET"])
    def get_queue():
        """
        Return the current queued tickets (ordered by urgency).
        Used by the server-rendered UI to show queue status.
        """
        tickets = []
        for t in queue_manager.peek_all():
            # t is a dict coming from Mongo
            tickets.append(
                {
                    "id": t.get("id"),
                    "subject": (t.get("subject", "")[:120] + "...") if len(t.get("subject", "")) > 120 else t.get("subject", ""),
                    "body": (t.get("body", "")[:240] + "...") if len(t.get("body", "")) > 240 else t.get("body", ""),
                    "customer": t.get("customer"),
                    "category": t.get("category"),
                    "urgency": round(float(t.get("urgency", 0.0)), 3),
                    "metadata": t.get("metadata", {}),
                    "status": t.get("status"),
                    "created_at": t.get("created_at"),
                }
            )
        return jsonify({"tickets": tickets})

    @app.route("/breaker", methods=["GET"])
    def breaker_status():
        """Return current circuit breaker state and simple metrics."""
        cb = get_circuit_breaker()
        open_since = cb.open_since
        cooldown_remaining = None
        if open_since is not None:
            elapsed = time.time() - open_since
            cooldown_remaining = max(0, int(cb.cooldown_sec - elapsed))
        return jsonify(
            {
                "state": cb.state,
                "consecutive_failures": cb.consecutive_failures,
                "half_open_tests": cb.half_open_tests,
                "half_open_successes": cb.half_open_successes,
                "cooldown_remaining": cooldown_remaining,
            }
        )

    return app

# backward-compatibility: create_app for run.py
app = create_app()

