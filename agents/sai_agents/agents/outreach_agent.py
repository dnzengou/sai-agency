"""OutreachAgent — outbound GTM communication for SAI Agency.

Generates a multi-touch cadence (cold email + LinkedIn) targeted at the AI /
ML / automation ICP, plus concrete message templates. Deterministic and
dependency-free so it runs anywhere; wire a real LLM by overriding
:meth:`run` — the ``AgentResult`` contract is stable.

Safety (KafCa Bl): every ICP-derived string in the context is screened by the
shared :class:`Blacklist` before it can shape output. A blocked probe surfaces
as a HIGH severity insight and short-circuits template generation for that
input, preventing prompt-injection contamination of the outreach loop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sai_agents.agents.base import BaseAgent
from sai_agents.kafca.blacklist import Blacklist
from sai_agents.kafca.impact import score_impact
from sai_agents.models import (
    AgentResult,
    EventType,
    Insight,
    Recommendation,
    Severity,
)

_DEFAULT_ICP = [
    "Head of Data / ML at a scaling B2B SaaS",
    "Founder of a vertical AI / agents startup",
    "Ops / RevOps lead automating manual workflows",
]

_CADENCE = [
    {"day": 0, "channel": "email", "purpose": "outcome-first cold open"},
    {"day": 2, "channel": "linkedin", "purpose": "connect + soft context"},
    {"day": 4, "channel": "email", "purpose": "proof / case study nudge"},
    {"day": 7, "channel": "linkedin", "purpose": "value-only follow-up"},
    {"day": 11, "channel": "email", "purpose": "breakup / permission close"},
]


class OutreachAgent(BaseAgent):
    """Outbound comms planner for GTM (email + LinkedIn cadence)."""

    name = "outreach"
    event_type = EventType.RECOMMENDATION

    def __init__(
        self,
        service: str = "sai-agents",
        blacklist: Optional[Blacklist] = None,
        spec: Optional[Dict[str, float]] = None,
        loadout: Optional[list] = None,
    ) -> None:
        super().__init__(service=service, spec=spec, loadout=loadout)
        self.blacklist = blacklist or Blacklist()

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        target = context.get("target_url")
        offer = context.get("offer") or "AI Agent Audit"
        icp: List[str] = list(context.get("icp") or _DEFAULT_ICP)

        insights: list[Insight] = []
        recommendations: list[Recommendation] = []

        # --- Bl: screen ICP inputs before they shape any generated copy ---
        safe_icp: list[str] = []
        for persona in icp:
            verdict = self.blacklist.screen(persona)
            if verdict.blocked:
                insights.append(
                    Insight(
                        title="Blocked jailbreak/injection in ICP input",
                        detail=f"ICP entry matched blacklist signature: {verdict.matched}",
                        severity=Severity.HIGH,
                        impact_score=score_impact(Severity.HIGH, confidence=0.9),
                        source_agent=self.name,
                        tags=["injection", "blacklist", "outreach"],
                    )
                )
                continue
            safe_icp.append(persona)

        # --- Cadence structure insight (higher signal density with more ICPs) ---
        insights.append(
            Insight(
                title="Multi-touch cadence over 11 days (email + LinkedIn)",
                detail=(
                    f"{len(_CADENCE)}-touch cadence balances reach and reply rate "
                    "without triggering deliverability penalties."
                ),
                severity=Severity.MEDIUM,
                impact_score=score_impact(
                    Severity.MEDIUM, confidence=0.7, signal_count=len(safe_icp) or 1
                ),
                source_agent=self.name,
                tags=["cadence", "outbound", "gtm"],
            )
        )

        if not safe_icp:
            # All ICPs were blocked — refuse to generate any templates.
            return AgentResult(
                agent=self.name,
                insights=insights,
                recommendations=recommendations,
                payload={
                    "target": target,
                    "offer": offer,
                    "cadence": _CADENCE,
                    "icp_safe": 0,
                    "icp_blocked": len(icp),
                    "templates": [],
                },
            )

        # --- Concrete message templates per ICP ---
        templates: list[dict[str, str]] = []
        for persona in safe_icp:
            email_subject = f"{offer.split()[0]} idea for {persona.split()[0]} teams"
            email_body = (
                f"Hi {{first_name}} — noticed you're a {persona}. "
                f"We ship a fixed-scope {offer} that de-risks a first AI / agents rollout "
                "in 2 weeks. Worth 15 minutes next week?"
            )
            linkedin_msg = (
                f"Hi {{first_name}}, connecting because {persona}s are exactly who our "
                f"{offer} was built for. No pitch — happy to share the audit checklist "
                "if useful."
            )
            templates.append(
                {
                    "persona": persona,
                    "email_subject": email_subject,
                    "email_body": email_body,
                    "linkedin_msg": linkedin_msg,
                }
            )
            recommendations.append(
                Recommendation(
                    action=f"Launch cadence for '{persona}' with subject: {email_subject!r}",
                    rationale="Persona-specific opener + productised offer lifts reply rate.",
                    priority=Severity.HIGH,
                    impact_score=score_impact(
                        Severity.HIGH, confidence=0.65, signal_count=2
                    ),
                    effort="low",
                    source_agent=self.name,
                )
            )

        recommendations.append(
            Recommendation(
                action="Cap sends at 40/day/domain and warm the sender inbox for 2 weeks",
                rationale="Deliverability discipline preserves the outbound channel long-term.",
                priority=Severity.MEDIUM,
                impact_score=score_impact(Severity.MEDIUM, confidence=0.75),
                effort="low",
                source_agent=self.name,
            )
        )
        recommendations.append(
            Recommendation(
                action=f"Route positive replies to a 'Book a discovery call' link on {target or 'the site'}",
                rationale="Close the loop between outreach and the site's inbound CTA.",
                priority=Severity.MEDIUM,
                impact_score=score_impact(Severity.MEDIUM, confidence=0.7),
                effort="low",
                source_agent=self.name,
            )
        )

        return AgentResult(
            agent=self.name,
            insights=insights,
            recommendations=recommendations,
            payload={
                "target": target,
                "offer": offer,
                "cadence": _CADENCE,
                "icp_safe": len(safe_icp),
                "icp_blocked": len(icp) - len(safe_icp),
                "templates": templates,
            },
        )
