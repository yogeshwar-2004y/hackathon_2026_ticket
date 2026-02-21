"""
Facade module exposing a shared CircuitBreaker instance.

This file imports the CircuitBreaker implementation (kept in m3 as the canonical
class for now) and exposes a module-level default instance plus a getter. This
allows other modules (background workers, tests) to reuse a single breaker and
share state across threads.
"""
from .m3.circuit_breaker import CircuitBreaker  # reuse the implementation in m3

# Module-level default breaker (shared singleton)
default_circuit_breaker = CircuitBreaker()

def get_circuit_breaker() -> CircuitBreaker:
    """Return the shared CircuitBreaker instance."""
    return default_circuit_breaker

