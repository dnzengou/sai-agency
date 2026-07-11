"""OrchestratorTeam — runs the full agent suite in a coherent order, threading
the ServiceTester's live findings into the downstream agents, and publishing
every result as an evolution signal to the KafCa stream.

Order:
  1. ServiceTester probes the live target (source of ground truth).
  2. Marketing / Sales-GTM / VulnRedTeam consume that context.
  3. All results are published as EvolutionEvents (E + Im + Bl guarded).
  4. A team-level FitnessScore is emitted for evo-metaclaw.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sai_agents.agents.marketing_agent import MarketingAgent
from sai_agents.agents.outreach_agent import OutreachAgent
from sai_agents.agents.sales_gtm_agent import SalesGTMAgent
from sai_agents.agents.vuln_redteam_agent import VulnRedTeamAgent
from sai_agents.config import Settings, get_settings
from sai_agents.deals.deal_sourcing_agent import DealSourcingAgent
from sai_agents.kafca.impact import aggregate_impact
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import get_logger
from sai_agents.models import (
    AgentResult,
    EventType,
    EvolutionEvent,
    FitnessScore,
)
from sai_agents.service_testers.service_tester_agent import ServiceTesterAgent

log = get_logger("orchestrator")


class OrchestratorTeam:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        publisher: Optional[KafkaEventPublisher] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.publisher = publisher or KafkaEventPublisher(self.settings)
        self.tester = ServiceTesterAgent(self.settings)
        self.marketing = MarketingAgent(service=self.settings.service_name)
        self.sales = SalesGTMAgent(service=self.settings.service_name)
        self.outreach = OutreachAgent(service=self.settings.service_name)
        self.security = VulnRedTeamAgent(service=self.settings.service_name)
        self.deals = DealSourcingAgent(service=self.settings.service_name)

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = dict(context or {})
        context.setdefault("target_url", self.settings.target_url)

        await self.publisher.start()
        try:
            # 1. Ground truth from the live site.
            tester_result = self.tester.execute(context)
            health = tester_result.payload.get("health", {})
            headers = context.get("headers") or health.get("headers") or {}

            downstream_ctx = {
                **context,
                "health": health,
                "headers": headers,
            }

            # 2. Downstream agents consume the live context.
            results: List[AgentResult] = [
                tester_result,
                self.marketing.execute(downstream_ctx),
                self.sales.execute(downstream_ctx),
                self.outreach.execute(downstream_ctx),
                self.security.execute(downstream_ctx),
                self.deals.execute(downstream_ctx),
            ]

            # 3. Publish each as an evolution event.
            emitters = [
                self.tester,
                self.marketing,
                self.sales,
                self.outreach,
                self.security,
                self.deals,
            ]
            events: List[EvolutionEvent] = [
                agent.to_event(result) for agent, result in zip(emitters, results)
            ]
            published = await self.publisher.publish_many(events)

            # 4. Team-level fitness for evo-metaclaw.
            team_fitness = self._team_fitness(results)
            team_event = EvolutionEvent(
                event_type=EventType.EVOLUTION_SIGNAL,
                service=self.settings.service_name,
                source_agent="orchestrator",
                impact_score=aggregate_impact(
                    [i for r in results for i in r.insights],
                    [rec for r in results for rec in r.recommendations],
                ),
                fitness=team_fitness,
                payload={"agents": [r.agent for r in results], "published": published},
            )
            await self.publisher.publish(team_event)

            summary = {
                "results": [r.model_dump() for r in results],
                "team_fitness": team_fitness.model_dump(),
                "events_published": published + 1,
                "high_impact_events": len(self.publisher.high_impact_events()),
                "kafka_active": self.publisher.kafka_active,
            }
            log.info(
                "orchestrator.done",
                agents=len(results),
                events_published=summary["events_published"],
                team_fitness=team_fitness.score,
            )
            return summary
        finally:
            await self.publisher.stop()

    def _team_fitness(self, results: List[AgentResult]) -> FitnessScore:
        tester = next((r for r in results if r.agent == "service_tester"), None)
        availability = 1.0 if (tester and tester.ok) else 0.0
        # More actionable, higher-impact recommendations => healthier feedback loop.
        rec_impacts = [rec.impact_score for r in results for rec in r.recommendations]
        actionability = round(sum(rec_impacts) / len(rec_impacts), 4) if rec_impacts else 0.0
        score = round(0.6 * availability + 0.4 * actionability, 4)
        return FitnessScore(
            genome="sai-agency-team",
            score=score,
            components={"availability": availability, "actionability": actionability},
            notes=f"{len(rec_impacts)} recommendations across {len(results)} agents",
        )
