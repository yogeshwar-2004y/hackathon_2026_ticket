"""
Circuit Breaker for Milestone 2 (ML inference protection).

This module provides a simple thread-safe CircuitBreaker class used by the
Milestone2 worker to protect calls to the heavier ML classifier (M2). It tracks
consecutive slow/failing calls and opens the circuit to force fallback to M1.

Behavior summary:
- CLOSED: allow ML calls and measure latency
- OPEN: immediately reject ML calls (use keyword fallback)
- HALF_OPEN: allow a small number of test ML calls; if they succeed the breaker closes

Configuration:
- max_latency_ms: threshold to consider an ML call "slow"
- failure_threshold: consecutive slow calls to trigger OPEN
- cooldown_sec: how long to keep OPEN before trying HALF_OPEN
- half_open_test_limit: number of test calls in HALF_OPEN to decide recovery
"""
from __future__ import annotations

import threading
import time
import logging
from typing import Callable, Tuple

logger = logging.getLogger(__name__)


class CircuitBreaker:
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
        self.half_open_tests = 0
        self.half_open_successes = 0

    def _open(self) -> None:
        self.state = CircuitBreaker.OPEN
        self.open_since = time.time()
        self.consecutive_failures = 0
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.warning("CircuitBreaker -> OPEN (cooldown %ds)", self.cooldown_sec)
        print(f"[CircuitBreaker] State -> OPEN (cooldown {self.cooldown_sec}s)")

    def _half_open(self) -> None:
        self.state = CircuitBreaker.HALF_OPEN
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.info("CircuitBreaker -> HALF_OPEN (test=%d)", self.half_open_test_limit)
        print(f"[CircuitBreaker] State -> HALF_OPEN (allow {self.half_open_test_limit} tests)")

    def _close(self) -> None:
        self.state = CircuitBreaker.CLOSED
        self.open_since = None
        self.consecutive_failures = 0
        self.half_open_tests = 0
        self.half_open_successes = 0
        logger.info("CircuitBreaker -> CLOSED")
        print("[CircuitBreaker] State -> CLOSED")

    def execute(self, m2_callable: Callable[[], Tuple[str, float]]) -> Tuple[bool, str, float, dict]:
        """
        Try to run the M2 callable (no args). The callable should return
        (category: str, urgency_score: float).

        Returns a tuple: (used_model: bool, category: str, urgency_score: float)
        - If used_model is False, caller should fallback to M1 results.
        """
        with self._lock:
            state = self.state
            # If OPEN, check cooldown
            if state == CircuitBreaker.OPEN:
                assert self.open_since is not None
                elapsed = time.time() - self.open_since
                if elapsed >= self.cooldown_sec:
                    self._half_open()
                    state = self.state
                else:
                    logger.debug("Circuit OPEN: skipping M2 (cooldown remaining %ds)", int(self.cooldown_sec - elapsed))
                    return False, "", 0.0

            # If HALF_OPEN, ensure we have available test slots
            if state == CircuitBreaker.HALF_OPEN:
                if self.half_open_tests >= self.half_open_test_limit:
                    logger.debug("HALF_OPEN test quota exhausted; skipping M2")
                    return False, "", 0.0
                # reserve a slot
                self.half_open_tests += 1

        # Execute M2 outside the lock and time it
        start = time.perf_counter()
        try:
            category, urgency_score = m2_callable()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.exception("M2 callable raised exception: %s", exc)
            slow = True
            category = ""
            urgency_score = 0.0
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            slow = elapsed_ms > self.max_latency_ms

        # Update state based on outcome
        with self._lock:
            info = {"elapsed_ms": elapsed_ms, "consecutive_failures": self.consecutive_failures}
            if slow:
                self.consecutive_failures += 1
                logger.warning("M2 slow/failure: %.1fms (failures=%d)", elapsed_ms, self.consecutive_failures)
                # If in HALF_OPEN, any slow result re-opens immediately
                if self.state == CircuitBreaker.HALF_OPEN:
                    self._open()
                    return False, "", 0.0, info
                if self.consecutive_failures >= self.failure_threshold:
                    self._open()
                    return False, "", 0.0, info
                # not tripped yet — still return model outcome if available
                if category == "":
                    return False, "", 0.0, info
                return True, category, urgency_score, info
            else:
                # success — reset failure counter
                self.consecutive_failures = 0
                if self.state == CircuitBreaker.HALF_OPEN:
                    self.half_open_successes += 1
                    logger.info("HALF_OPEN success (%d/%d)", self.half_open_successes, self.half_open_test_limit)
                    if self.half_open_successes >= self.half_open_test_limit:
                        self._close()
                info = {"elapsed_ms": elapsed_ms, "consecutive_failures": 0}
                return True, category, urgency_score, info

