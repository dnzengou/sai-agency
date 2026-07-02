"""DealSourcingAgent — wraps the KafCade pipeline as a first-class agent.

It runs the cascade, turns the sourced deals into agent insights +
recommendations (top opportunities to pursue), and emits an evolution signal so
the deal feed participates in the same KafCa / evo-metaclaw loop as the rest of
the suite.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sai_agents.agents.base import BaseAgent
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.models import (
    AgentResult,
    EventType,
    Insight,
    Recommendation,
    Severity,
)


class DealSourcingAgent(BaseAgent):
    name = "deal_sourcing"
    event_type = EventType.DEAL_SIGNAL

    def __init__(self, service: str = "sai-agents", pipeline: Optional[KafCadePipeline] = None) -> None:
        super().__init__(service=service)
        self.pipeline = pipeline or KafCadePipeline()

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        top_n = int(context.get("top_n", 5))
        deals = self.pipeline.collect()
        dataset = self.pipeline.build_dataset(deals)

        insights: List[Insight] = []
        recommendations: List[Recommendation] = []
        for deal in deals[:top_n]:
            insights.append(
                Insight(
                    title=f"[{deal.country}] {deal.title}",
                    detail=f"{deal.type.value} · {deal.org} · impact {deal.impact_score}",
                    severity=deal.priority,
                    impact_score=deal.impact_score,
                    source_agent=self.name,
                    tags=[deal.region, deal.country, deal.type.value, deal.sector],
                )
            )
            recommendations.append(
                Recommendation(
                    action=deal.next_action,
                    rationale=f"{deal.type.value} in {deal.country} (owner: {deal.owner})",
                    priority=deal.priority,
                    impact_score=deal.impact_score,
                    effort="medium",
                    source_agent=self.name,
                )
            )

        return AgentResult(
            agent=self.name,
            ok=len(deals) > 0,
            insights=insights,
            recommendations=recommendations,
            payload={
                "summary": dataset["summary"],
                "sources": self.pipeline.registry.source_names,
            },
        )
