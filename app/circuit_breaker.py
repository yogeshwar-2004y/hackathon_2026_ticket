"""
Facade exposing a shared CircuitBreaker instance for the app package.
Uses the implementation in app.milestone2.circuit_breaker.
"""
from app.milestone2.circuit_breaker import CircuitBreaker

# Shared singleton breaker
default_circuit_breaker = CircuitBreaker()

def get_circuit_breaker() -> CircuitBreaker:
    return default_circuit_breaker

