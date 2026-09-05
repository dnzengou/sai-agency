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

    def __init__(
        self,
        service: str = "sai-agents",
        pipeline: Optional[KafCadePipeline] = None,
        spec: Optional[Dict[str, float]] = None,
        loadout: Optional[list] = None,
    ) -> None:
        super().__init__(service=service, spec=spec, loadout=loadout)
        self.pipeline = pipeline or KafCadePipeline()

    def _arm_rank(self, deals: list) -> list:
        """Order deals by ARM priority, tilted by the evolved champion spec and
        the EvoSkillOpt loadout.

        Unevolved (no spec and no loadout) => keep the pipeline's impact
        ordering. When a champion spec is present, ``recency_weight`` tilts
        toward immediately actionable (open/upcoming) deals and ``impact_bias``
        sharpens the pull toward open opportunities. The EvoSkillOpt loadout
        adds a bonus for deals whose attributes (region/country/type/sector)
        match the skills that have historically paid off — gated by the evolved
        ``exploration`` knob, so a genome only chases learned skills as much as
        it has evolved to explore. Deal impact scores are never mutated — only
        the *order in which* ARM surfaces them — so evolution reprioritises the
        pipeline without gaming its own fitness metric.
        """
        if self.spec is None and not self.loadout:
            return deals
        rw = self.spec_val("recency_weight")
        ib = self.spec_val("impact_bias")
        ex = self.spec_val("exploration")
        loadout = {s.lower() for s in self.loadout}

        def key(d):
            actionable = 1.0 if d.stage in ("open", "upcoming") else 0.4
            openness = 1.0 if d.stage in ("open", "upcoming") else 0.0
            skill_match = self._skill_match(d, loadout)
            return (
                (1 - rw) * d.impact_score
                + rw * actionable
                + 0.1 * ib * openness
                + 0.15 * ex * skill_match
            )

        return sorted(deals, key=key, reverse=True)

    @staticmethod
    def _skill_match(deal, loadout: set) -> float:
        """Fraction of the loadout matched by this deal's ARM attributes."""
        if not loadout:
            return 0.0
        attrs = {
            str(deal.region).lower(),
            str(deal.country).lower(),
            str(deal.type.value).lower(),
            str(deal.sector).lower(),
        }
        return len(attrs & loadout) / len(loadout)

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        top_n = int(context.get("top_n", 5))
        deals = self.pipeline.collect()
        dataset = self.pipeline.build_dataset(deals)
        ranked = self._arm_rank(deals)
        loadout = {s.lower() for s in self.loadout}

        surfaced = ranked[:top_n]
        loadout_matched = sum(1 for d in surfaced if self._skill_match(d, loadout) > 0)

        insights: List[Insight] = []
        recommendations: List[Recommendation] = []
        for deal in surfaced:
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
                "loadout": sorted(loadout),
                "loadout_matched": loadout_matched,
            },
        )
