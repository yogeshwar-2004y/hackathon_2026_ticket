import os
import time
import uuid
from flask import current_app, Flask, request, jsonify
from .models import Ticket
from .classifier import keyword_classify
from .queue_manager import queue_manager
from .background import background_service

MODE = os.getenv("ROUTER_MODE", "m2").lower()

def create_app():
    app = Flask(__name__)

    # ensure background service initialized (only in m2)
    if MODE == "m2":
        background_service.start()

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
            queue_manager.push(ticket)
            return jsonify(
                {"ticket_id": ticket.id, "category": ticket.category, "urgency": round(ticket.urgency, 2), "status": ticket.status}
            ), 200

        # Milestone 2 async: accept quickly, process in background
        else:
            # store minimal info and enqueue background processing
            ticket.status = "received"
            background_service.submit(ticket)
            return jsonify({"ticket_id": ticket.id, "status": "accepted"}), 202

    return app

# backward-compatibility: create_app for run.py
app = create_app()

