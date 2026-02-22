"""
circuit_breaker.py

Placeholder for a circuit breaker that falls back to keyword routing if the model is slow/unavailable.

Planned responsibilities:
- Measure model call latency and maintain a moving window of recent latencies
- If average latency or error rate crosses thresholds, flip to "open" and route to keyword classifier
- Provide a decorator/factory to wrap model calls:
    with circuit_breaker.guard():
        call_model(...)

No working code provided in this milestone — this file is intentionally a stub.
"""
# TODO: implement in Milestone 3
pass

"""
Circuit Breaker for ML inference (app-level).

Provides a simple CircuitBreaker class to protect the ML/model calls used during
Milestone 2. The breaker tracks wall-clock latency of model calls and opens the
circuit after a number of consecutive "slow" or failed calls. When OPEN the
breaker immediately falls back to keyword-based routing.

States:
- CLOSED: normal operation, measure latencies and count consecutive slow calls
- OPEN: all requests immediately use keyword fallback; stays OPEN for cooldown_sec
- HALF_OPEN: after cooldown allow a small number of test calls; if they succeed
  (fast) the breaker CLOSEs again, otherwise it re-opens

Usage:
  cb = CircuitBreaker()
  category, urgency = cb.execute(classify_func, urgency_func, ticket)

The classify_func should accept the ticket and return a category string.
The urgency_func should accept the ticket and return a float urgency in [0,1].
"""
from __future__ import annotations

import time
import threading
import logging
from typing import Callable, Tuple

from .classifier import keyword_classify
from .models import Ticket

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Simple thread-safe circuit breaker for ML inference latency.

    Parameters:
    - max_latency_ms: latency threshold in milliseconds to consider a call "slow"
    - failure_threshold: number of consecutive slow/failed calls to OPEN the circuit
    - cooldown_sec: seconds to wait while OPEN before transitioning to HALF_OPEN
    - half_open_test_limit: number of allowed test calls in HALF_OPEN required to
      consider the model healthy again
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        max_latency_ms: int = 500,
        failure_threshold: int = 4,
        cooldown_sec: int = 60,
        half_open_test_limit: int = 2,
    ) -> None:
        self.max_latency_ms = max_latency_ms
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self.half_open_test_limit = half_open_test_limit

        self._lock = threading.Lock()
        self.state = CircuitBreaker.CLOSED
        self.consecutive_failures = 0
        self.open_since: float | None = None
        # HALF_OPEN counters
        self.half_open_tests = 0
        self.half_open_successes = 0

    def _keyword_fallback(self, ticket: Ticket) -> Tuple[str, float]:
        """Use the existing keyword classifier as a safe fallback."""
        cat, urg = keyword_classify(ticket.subject, ticket.body)
        return cat, urg

    def _open_circuit(self) -> None:
        self.state = CircuitBreaker.OPEN
        self.open_since = time.time()
        self.consecutive_failures = 0
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.warning("CircuitBreaker -> OPEN (cooldown %ds)", self.cooldown_sec)
        print(f"[CircuitBreaker] State change: CLOSED/HALF_OPEN -> OPEN (cooldown {self.cooldown_sec}s)")

    def _close_circuit(self) -> None:
        self.state = CircuitBreaker.CLOSED
        self.open_since = None
        self.consecutive_failures = 0
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.info("CircuitBreaker -> CLOSED")
        print("[CircuitBreaker] State change: HALF_OPEN -> CLOSED")

    def _to_half_open(self) -> None:
        self.state = CircuitBreaker.HALF_OPEN
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.info("CircuitBreaker -> HALF_OPEN (test calls allowed=%d)", self.half_open_test_limit)
        print(f"[CircuitBreaker] State change: OPEN -> HALF_OPEN (allow {self.half_open_test_limit} test calls)")

    def execute(
        self,
        classify_func: Callable[[Ticket], str],
        urgency_func: Callable[[Ticket], float],
        ticket: Ticket,
    ) -> Tuple[str, float]:
        """
        Execute model classification & urgency functions under circuit protection.

        - Returns (category, urgency).
        - If the circuit is OPEN, returns keyword fallback immediately.
        - Measures latency of classify_func and urgency_func (separately).
        - Counts a call as a failure if either call exceeds max_latency_ms or raises.
        """
        # Quick state check with lock
        with self._lock:
            state = self.state
            if state == CircuitBreaker.OPEN:
                assert self.open_since is not None
                elapsed = time.time() - self.open_since
                if elapsed >= self.cooldown_sec:
                    # Transition to HALF_OPEN and allow a few test calls
                    self._to_half_open()
                    state = self.state
                else:
                    logger.debug("Circuit OPEN; returning keyword fallback (elapsed=%ds)", int(elapsed))
                    return self._keyword_fallback(ticket)

        # If HALF_OPEN, check whether we still allow a test call
        if state == CircuitBreaker.HALF_OPEN:
            with self._lock:
                if self.half_open_tests >= self.half_open_test_limit:
                    # Already used test quota; fall back to keyword until state changes
                    logger.debug("HALF_OPEN test quota exhausted; returning keyword fallback")
                    return self._keyword_fallback(ticket)
                # Reserve a test slot
                self.half_open_tests += 1

        # Perform the model calls and measure latencies outside the lock
        classify_latency_ms = None
        urgency_latency_ms = None
        try:
            t0 = time.perf_counter()
            category = classify_func(ticket)
            t1 = time.perf_counter()
            classify_latency_ms = (t1 - t0) * 1000.0

            t2 = time.perf_counter()
            urgency = urgency_func(ticket)
            t3 = time.perf_counter()
            urgency_latency_ms = (t3 - t2) * 1000.0

            slow = (
                (classify_latency_ms is not None and classify_latency_ms > self.max_latency_ms)
                or (urgency_latency_ms is not None and urgency_latency_ms > self.max_latency_ms)
            )
        except Exception as exc:  # treat exceptions as failures/slow
            logger.exception("Model call raised exception: %s", exc)
            slow = True
            category = None  # type: ignore
            urgency = 0.0

        # Update breaker state based on observed result
        with self._lock:
            if slow:
                # count failure
                self.consecutive_failures += 1
                logger.warning(
                    "Model call slow/failure (classify=%.1fms, urgency=%.1fms) -> failures=%d",
                    classify_latency_ms or -1.0,
                    urgency_latency_ms or -1.0,
                    self.consecutive_failures,
                )
                # If we are in HALF_OPEN, any slow result re-opens immediately
                if self.state == CircuitBreaker.HALF_OPEN:
                    self._open_circuit()
                    return self._keyword_fallback(ticket)

                if self.consecutive_failures >= self.failure_threshold:
                    self._open_circuit()
                    return self._keyword_fallback(ticket)
                # Not yet tripped: return model result (best-effort) but count failure
                # If category is None due to exception, fallback
                if category is None:
                    return self._keyword_fallback(ticket)
                # still return model outputs despite being slow (until threshold)
                return category, urgency
            else:
                # success: clear failures
                self.consecutive_failures = 0
                # If HALF_OPEN, record success and possibly close circuit
                if self.state == CircuitBreaker.HALF_OPEN:
                    self.half_open_successes += 1
                    logger.info(
                        "HALF_OPEN test success (%d/%d)",
                        self.half_open_successes,
                        self.half_open_test_limit,
                    )
                    if self.half_open_successes >= self.half_open_test_limit:
                        self._close_circuit()
                return category, urgency

