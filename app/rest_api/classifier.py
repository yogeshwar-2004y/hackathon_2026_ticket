import os
import re
from typing import Tuple, List
import logging

try:
    from transformers import pipeline
except ImportError:
    pipeline = None

logger = logging.getLogger(__name__)

# Candidate categories for zero-shot classification
CANDIDATES = ["Billing", "Technical", "Legal"]
M2_MODEL_ID = os.getenv("M2_MODEL_ID", "typeform/distilbert-base-uncased-mnli")
M2_MODEL_PATH = os.getenv("M2_MODEL_PATH", "").strip()
HF_LOCAL_ONLY = os.getenv("HF_LOCAL_ONLY", "0").strip().lower() in {"1", "true", "yes"}

_nlp_pipeline = None

def _get_pipeline():
    global _nlp_pipeline
    if _nlp_pipeline is None:
        if pipeline is None:
            # Fallback mock for testing in broken environments
            class MockPipeline:
                def __call__(self, text, candidates, multi_label=False):
                    return {"labels": [candidates[0]], "scores": [0.9]}
            _nlp_pipeline = MockPipeline()
        else:
            # Load from local path when provided, otherwise use HF model id.
            model_ref = M2_MODEL_PATH if M2_MODEL_PATH else M2_MODEL_ID
            _nlp_pipeline = pipeline(
                "zero-shot-classification",
                model=model_ref,
                local_files_only=HF_LOCAL_ONLY,
            )
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

