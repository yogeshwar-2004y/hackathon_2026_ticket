import json
import logging
from app.milestone2.celery_config import celery_app
from app.rest_api.classifier import model_classify
from app.rest_api.circuit_breaker import get_circuit_breaker
from app.rest_api.models import Ticket

logger = logging.getLogger(__name__)

def score_to_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    elif score >= 0.4:
        return "medium"
    return "low"

cb = get_circuit_breaker()

@celery_app.task(name="app.milestone2.celery_worker.process_ticket")
def process_ticket(ticket_dict):
    """
    Celery task that receives a ticket dictionary, classifies it,
    and then forwards it to Milestone 3 queues (high, medium, low).
    """
    logger.info(f"Worker received ticket: {ticket_dict.get('id')}")
    
    ticket = Ticket(
        id=ticket_dict.get("id"),
        subject=ticket_dict.get("subject", ""),
        body=ticket_dict.get("body", ""),
        customer=ticket_dict.get("customer", "")
    )
    
    # We define the wrappers for CircuitBreaker
    def classify_wrapper(t):
        lab, conf, urg = model_classify(t.subject, t.body)
        t.metadata["_m2_urgency_cache"] = float(urg)
        return lab
        
    def urgency_wrapper(t):
        if "_m2_urgency_cache" in t.metadata:
            return t.metadata["_m2_urgency_cache"]
        lab, conf, urg = model_classify(t.subject, t.body)
        return float(urg)
        
    try:
        final_cat, final_urg_score = cb.execute(classify_wrapper, urgency_wrapper, ticket)
        final_label = score_to_label(final_urg_score)
    except Exception as e:
        logger.exception("Classification failed")
        from app.rest_api.classifier import keyword_classify
        final_cat, m1_score = keyword_classify(ticket.subject, ticket.body)
        final_label = score_to_label(m1_score)

    logger.info(f"Ticket {ticket.id} classified as {final_cat} with urgency {final_label}")
    
    # Forward JSON text to Milestone 3 while preserving its
    # existing signature: process_ticket(ticket_text, priority)
    queue_payload = {
        "ticket_id": ticket.id,
        "status": "processed",
        "category": final_cat,
        "urgency": final_label,
        "subject": ticket.subject,
        "message": ticket.body,
        "customer": ticket.customer,
    }
    ticket_text = json.dumps(queue_payload, ensure_ascii=True)
    celery_app.send_task(
        "Main.process_ticket",
        args=[ticket_text, final_label],
        queue=final_label
    )
    logger.info(f"Ticket {ticket.id} forwarded to queue: {final_label}")
    
    return {"ticket_id": ticket.id, "status": "processed", "category": final_cat, "urgency": final_label}
