"""VulnRedTeamAgent — lightweight, non-intrusive security posture checks for
the live site plus a red-team pass on agent inputs.

This performs only passive/header-level checks against data already gathered by
the ServiceTester. It never launches intrusive scans, and it uses the KafCa
Blacklist to red-team the input context itself for injection attempts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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

# Security response headers we expect on a hardened static site.
_EXPECTED_HEADERS = {
    "strict-transport-security": "Enforce HTTPS (HSTS).",
    "content-security-policy": "Mitigate XSS / injection via CSP.",
    "x-content-type-options": "Prevent MIME sniffing (nosniff).",
    "x-frame-options": "Prevent clickjacking.",
    "referrer-policy": "Limit referrer leakage.",
}


class VulnRedTeamAgent(BaseAgent):
    name = "vuln_redteam"
    event_type = EventType.SECURITY_FINDING

    def __init__(self, service: str = "sai-agents", blacklist: Optional[Blacklist] = None) -> None:
        super().__init__(service=service)
        self.blacklist = blacklist or Blacklist()

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        insights: list[Insight] = []
        recommendations: list[Recommendation] = []

        # --- Red-team the input itself (Bl safety pattern) ---
        probes = context.get("probes") or []
        for probe in probes:
            verdict = self.blacklist.screen(probe)
            if verdict.blocked:
                insights.append(
                    Insight(
                        title="Blocked jailbreak/injection probe",
                        detail=f"Input matched blacklist signature: {verdict.matched}",
                        severity=Severity.HIGH,
                        impact_score=score_impact(Severity.HIGH, confidence=0.9),
                        source_agent=self.name,
                        tags=["injection", "blacklist", "redteam"],
                    )
                )

        # --- Passive header posture check ---
        headers = {
            str(k).lower(): v for k, v in (context.get("headers") or {}).items()
        }
        missing = [h for h in _EXPECTED_HEADERS if h not in headers]
        for header in missing:
            insights.append(
                Insight(
                    title=f"Missing security header: {header}",
                    detail=_EXPECTED_HEADERS[header],
                    severity=Severity.MEDIUM,
                    impact_score=score_impact(Severity.MEDIUM, confidence=0.8),
                    source_agent=self.name,
                    tags=["headers", "hardening"],
                )
            )
        if missing:
            recommendations.append(
                Recommendation(
                    action=f"Add security headers via netlify.toml: {', '.join(missing)}",
                    rationale="Static-site security headers are a cheap, high-value hardening step.",
                    priority=Severity.MEDIUM,
                    impact_score=score_impact(Severity.MEDIUM, confidence=0.8),
                    effort="low",
                    source_agent=self.name,
                )
            )

        return AgentResult(
            agent=self.name,
            insights=insights,
            recommendations=recommendations,
            payload={"missing_headers": missing, "probes_screened": len(probes)},
        )
