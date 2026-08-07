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
from sai_agents.models import (
    AgentResult,
    EventType,
    EvolutionEvent,
    Recommendation,
    Severity,
)

# Neutral spec — a genome that has never been evolved behaves exactly as before.
_NEUTRAL_SPEC = {
    "impact_bias": 0.5,
    "exploration": 0.5,
    "risk_tolerance": 0.5,
    "recency_weight": 0.5,
}


class BaseAgent(ABC):
    #: Stable identifier used as event source + partition key.
    name: str = "base"
    #: Event type this agent emits by default.
    event_type: EventType = EventType.AGENT_RUN

    def __init__(
        self,
        service: str = "sai-agents",
        spec: Optional[Dict[str, float]] = None,
        loadout: Optional[list] = None,
    ) -> None:
        self.service = service
        # EvoForge champion spec + EvoSkillOpt loadout for this genome. When
        # absent the agent runs at its pre-evolution baseline (spec is None).
        self.spec: Optional[Dict[str, float]] = dict(spec) if spec else None
        self.loadout: list = list(loadout) if loadout else []
        self.log = get_logger(f"agent.{self.name}")

    # ------------------------------------------------------------------ #
    def spec_val(self, knob: str) -> float:
        """Read one evolved knob (neutral 0.5 when unevolved)."""
        return (self.spec or _NEUTRAL_SPEC).get(knob, 0.5)

    def _apply_spec(self, result: AgentResult) -> AgentResult:
        """Let the evolved spec shape the result — breadth only, never impact.

        The ``exploration`` knob, when evolved high, broadens the agent with one
        exploratory recommendation seeded by the top evolved skill. Impact
        scores are never rescaled here, so evolution cannot game its own fitness
        metric by inflating what it reports — it can only change *what* it does.
        """
        if self.spec is None or not result.ok:
            return result
        if self.spec_val("exploration") > 0.6 and self.loadout:
            top = self.loadout[0]
            result.recommendations.append(
                Recommendation(
                    action=f"Exploratory: double down on '{top}' (top evolved skill)",
                    rationale=(
                        "EvoSkillOpt ranks this skill highest by accrued impact and "
                        "this genome's evolved exploration knob favours broadening here."
                    ),
                    priority=Severity.MEDIUM,
                    impact_score=0.5,
                    effort="low",
                    source_agent=self.name,
                )
            )
        return result

    @abstractmethod
    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Do the agent's work synchronously and return a typed result."""

    # ------------------------------------------------------------------ #
    def execute(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Safe wrapper around :meth:`run` — never raises, always metered."""
        start = time.perf_counter()
        try:
            result = self.run(context or {})
            result = self._apply_spec(result)
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
        payload = result.payload
        if self.spec is not None:
            # Record the spec that was active so the trajectory is honest about
            # which candidate produced it — this is what makes EvoForge's
            # accept/reject on the next turn meaningful.
            payload = {**payload, "genome_spec": self.spec, "loadout": self.loadout[:5]}
        return EvolutionEvent(
            event_type=self.event_type,
            service=self.service,
            source_agent=self.name,
            impact_score=impact,
            payload=payload,
            insights=result.insights,
            recommendations=result.recommendations,
            fitness=result.fitness,
        )
