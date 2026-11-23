"""SalesGTMAgent — go-to-market and pipeline insights for acquiring clients for
SAI Agency's AI / ML / automation services.
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


class SalesGTMAgent(BaseAgent):
    name = "sales_gtm"
    event_type = EventType.RECOMMENDATION

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}

        insights = [
            Insight(
                title="No visible primary CTA / booking path",
                detail="A single 'Book a discovery call' CTA shortens the sales cycle.",
                severity=Severity.HIGH,
                impact_score=score_impact(Severity.HIGH, confidence=0.65, signal_count=2),
                source_agent=self.name,
                tags=["cta", "pipeline", "conversion"],
            ),
            Insight(
                title="Productise a lead-gen offer",
                detail=(
                    "A fixed-scope 'AI Agent Audit' or 'ML feasibility sprint' "
                    "lowers the barrier to a first paid engagement."
                ),
                severity=Severity.MEDIUM,
                impact_score=score_impact(Severity.MEDIUM, confidence=0.6),
                source_agent=self.name,
                tags=["offer", "productisation"],
            ),
        ]
        recommendations = [
            Recommendation(
                action="Add a single 'Book a discovery call' CTA above the fold + footer",
                rationale="One clear next step converts more warm traffic.",
                priority=Severity.HIGH,
                impact_score=score_impact(Severity.HIGH, confidence=0.7),
                effort="low",
                source_agent=self.name,
            ),
            Recommendation(
                action="Launch a fixed-price 'AI Agent Audit' entry offer",
                rationale="Low-commitment paid offers seed larger engagements.",
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
            payload={"motion": "inbound", "target": context.get("target_url")},
        )
