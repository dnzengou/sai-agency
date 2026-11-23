"""KafCa — Kafka Event sourcing (E) + Impact tracking (Im) + Bl.

Bl = Blacklist + Circuit Breaker for safe self-evolution.
"""

from sai_agents.kafca.blacklist import Blacklist, BlacklistVerdict
from sai_agents.kafca.circuit_breaker import BreakerState, CircuitBreaker, CircuitOpenError
from sai_agents.kafca.impact import score_impact
from sai_agents.kafca.publisher import KafkaEventPublisher

__all__ = [
    "Blacklist",
    "BlacklistVerdict",
    "CircuitBreaker",
    "CircuitOpenError",
    "BreakerState",
    "score_impact",
    "KafkaEventPublisher",
]
