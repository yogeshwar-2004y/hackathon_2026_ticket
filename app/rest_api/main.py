import os
import time
import uuid
from flask import current_app, Flask, request, jsonify, render_template
from flask_cors import CORS
from .models import Ticket
from .classifier import keyword_classify
from .queue_manager import queue_manager
from .circuit_breaker import get_circuit_breaker
from .ws_status import init_ws, publish_status

MODE = os.getenv("ROUTER_MODE", "m2").lower()

def create_app():
    # Tell Flask to look for templates/static inside the package
    app = Flask(__name__, template_folder="templates", static_folder="static")
    # Allow cross-origin requests from the frontend dev server (and others).
    # In production restrict origins appropriately.
    CORS(app, resources={r"/*": {"origins": "*"}})
    init_ws(app)

    @app.route("/", methods=["GET"])
    def index():
        # simple server-rendered UI for submitting tickets and viewing queue
        return render_template("index.html", mode=MODE)

    @app.route("/tickets", methods=["POST"])
    @app.route("/submit", methods=["POST"])
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

        # Milestone 2 async: accept quickly, process via Celery worker
        else:
            ticket.status = "received"
            try:
                queue_manager.tickets.replace_one(
                    {"_id": ticket.id},
                    {
                        "_id": ticket.id,
                        "id": ticket.id,
                        "subject": ticket.subject,
                        "body": ticket.body,
                        "customer": ticket.customer,
                        "category": None,
                        "urgency": 0.0,
                        "status": "received",
                        "metadata": {},
                        "created_at": ticket.created_at,
                    },
                    upsert=True,
                )
                publish_status(ticket.id, "received")
            except Exception:
                pass
            ticket_data = {
                "id": ticket.id,
                "subject": ticket.subject,
                "body": ticket.body,
                "customer": ticket.customer,
                "created_at": ticket.created_at,
            }
            from app.milestone2.celery_worker import process_ticket
            process_ticket.delay(ticket_data)
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

