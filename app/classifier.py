import re
from typing import Tuple
import logging

from transformers import pipeline

logger = logging.getLogger(__name__)

# Candidate categories for zero-shot classification
CANDIDATES = ["Billing", "Technical", "Legal"]

_nlp_pipeline = None

def _get_pipeline():
    global _nlp_pipeline
    if _nlp_pipeline is None:
        # Load a lightweight MNLI model for zero-shot classification (CPU)
        _nlp_pipeline = pipeline("zero-shot-classification", model="typeform/distilbert-base-uncased-mnli")
    return _nlp_pipeline

def keyword_classify(subject: str, body: str) -> Tuple[str, float]:
    """Simple keyword + regex-based classification (Milestone 1)."""
    text = f"{subject}\n{body}".lower()
    # Category rules
    if re.search(r"\bbill(ing|ed|s)?\b|\bcharge|\binvoice\b", text):
        category = "Billing"
    elif re.search(r"\b(error|bug|fail|crash|broken|server|timeout)\b", text):
        category = "Technical"
    elif re.search(r"\b(contract|law|legal|terms|privacy|compliance)\b", text):
        category = "Legal"
    else:
        category = "Technical"  # default

    # Urgency heuristics via regex
    urgency = 0.0
    if re.search(r"\burgent\b|\basap\b|\bimmediately\b", text):
        urgency += 0.6
    if re.search(r"!!+", text):
        urgency += 0.2
    if re.search(r"\bbroken\b|\bdown\b|\bnot working\b", text):
        urgency += 0.3
    # clamp to [0,1]
    urgency = max(0.0, min(1.0, urgency))
    return category, urgency

def model_classify(subject: str, body: str) -> Tuple[str, float, float]:
    """
    Use a zero-shot transformer to classify and estimate urgency (Milestone 2).
    Returns (category, confidence, urgency_estimate).
    """
    nlp = _get_pipeline()
    text = f"{subject}\n{body}"
    # Run zero-shot classification
    resp = nlp(text, CANDIDATES, multi_label=False)
    # resp has 'labels' and 'scores'
    label = resp["labels"][0]
    score = float(resp["scores"][0])

    # Rough urgency estimate: map score -> [0.2, 0.7] then boost with keywords
    urgency = 0.2 + 0.5 * score
    # keyword boost
    if re.search(r"\burgent\b|\basap\b|\bimmediately\b|!!+", text.lower()):
        urgency += 0.2
    urgency = max(0.0, min(1.0, urgency))

    logger.debug("Model classification: label=%s score=%.3f urgency=%.3f", label, score, urgency)
    return label, score, urgency

