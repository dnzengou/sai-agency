"""MarketingAgent — surfaces positioning / content / acquisition insights for
the SAI Agency site and offerings.

Deterministic, dependency-free heuristics by default so it runs anywhere. Wire
a real LLM by overriding :meth:`run` — the ``AgentResult`` contract is stable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sai_agents.agents.base import BaseAgent
from sai_agents.kafca.impact import score_impact
from sai_agents.models import (
    AgentResult,
    EventType,
    Insight,
    Recommendation,
    Severity,
)


class MarketingAgent(BaseAgent):
    name = "marketing"
    event_type = EventType.INSIGHT

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        health = context.get("health") or {}
        site_ok = bool(health.get("ok", True))

        insights = [
            Insight(
                title="Sharpen above-the-fold value proposition",
                detail=(
                    "State the concrete outcome SAI Agency delivers (custom AI "
                    "agents, ML/data automation) in the hero within 5 words."
                ),
                severity=Severity.HIGH,
                impact_score=score_impact(Severity.HIGH, confidence=0.7, signal_count=2),
                source_agent=self.name,
                tags=["positioning", "hero", "conversion"],
            ),
            Insight(
                title="Add proof / case studies",
                detail="Social proof from prior ML/data engagements lifts trust and CTR.",
                severity=Severity.MEDIUM,
                impact_score=score_impact(Severity.MEDIUM, confidence=0.6, signal_count=1),
                source_agent=self.name,
                tags=["trust", "content"],
            ),
        ]
        if not site_ok:
            insights.append(
                Insight(
                    title="Site unreachable — marketing spend at risk",
                    detail="Paid/organic traffic is landing on a broken page.",
                    severity=Severity.CRITICAL,
                    impact_score=score_impact(Severity.CRITICAL, confidence=0.9),
                    source_agent=self.name,
                    tags=["availability", "waste"],
                )
            )

        recommendations = [
            Recommendation(
                action="Rewrite hero headline + subhead around a single outcome",
                rationale="Clear outcome-first messaging is the top conversion lever.",
                priority=Severity.HIGH,
                impact_score=score_impact(Severity.HIGH, confidence=0.7),
                effort="low",
                source_agent=self.name,
            ),
            Recommendation(
                action="Publish 2 short case studies with measurable results",
                rationale="Concrete outcomes de-risk the buyer decision.",
                priority=Severity.MEDIUM,
                impact_score=score_impact(Severity.MEDIUM, confidence=0.6),
                effort="medium",
                source_agent=self.name,
            ),
        ]
        return AgentResult(
            agent=self.name,
            insights=insights,
            recommendations=recommendations,
            payload={"channel": "website", "target": context.get("target_url")},
        )
