"""BaseAgent — common contract for every agent.

An agent takes a context dict, does its work, and returns a typed
``AgentResult``. The base wraps every run so it: (1) never raises to the caller
(returns ``ok=False`` instead), (2) records metrics, and (3) converts the
result into an ``EvolutionEvent`` for the KafCa stream.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from sai_agents.kafca.impact import aggregate_impact
from sai_agents.logging_setup import get_logger
from sai_agents.metrics import AGENT_RUNS, IMPACT_GAUGE, RUN_LATENCY
from sai_agents.models import AgentResult, EventType, EvolutionEvent


class BaseAgent(ABC):
    #: Stable identifier used as event source + partition key.
    name: str = "base"
    #: Event type this agent emits by default.
    event_type: EventType = EventType.AGENT_RUN

    def __init__(self, service: str = "sai-agents") -> None:
        self.service = service
        self.log = get_logger(f"agent.{self.name}")

    @abstractmethod
    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Do the agent's work synchronously and return a typed result."""

    # ------------------------------------------------------------------ #
    def execute(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Safe wrapper around :meth:`run` — never raises, always metered."""
        start = time.perf_counter()
        try:
            result = self.run(context or {})
        except Exception as exc:  # defensive: an agent bug must not kill the team
            self.log.error("agent.run.error", error=str(exc))
            result = AgentResult(agent=self.name, ok=False, error=str(exc))
        finally:
            RUN_LATENCY.labels(self.name).observe(time.perf_counter() - start)

        AGENT_RUNS.labels(self.name, str(result.ok).lower()).inc()
        IMPACT_GAUGE.labels(self.name).set(result.aggregate_impact)
        self.log.info(
            "agent.run.done",
            ok=result.ok,
            insights=len(result.insights),
            recommendations=len(result.recommendations),
            impact=result.aggregate_impact,
        )
        return result

    def to_event(self, result: AgentResult) -> EvolutionEvent:
        """Convert an :class:`AgentResult` into a KafCa evolution event."""
        impact = aggregate_impact(result.insights, result.recommendations)
        return EvolutionEvent(
            event_type=self.event_type,
            service=self.service,
            source_agent=self.name,
            impact_score=impact,
            payload=result.payload,
            insights=result.insights,
            recommendations=result.recommendations,
            fitness=result.fitness,
        )
