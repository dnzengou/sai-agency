"""ServiceTesterAgent — the continuous feedback / improvement loop.

It health-checks the live target (default ``https://sai-agency-deals-radar.netlify.app``),
derives insights, computes a ``FitnessScore`` for the current deployment
genome, and publishes an ``EvolutionEvent`` so evo-metaclaw / evolved-skill-opt
can consume it for population-based skill evolution.

Network access is optional: uses only the Python stdlib (``urllib``) and
degrades gracefully to a structured error signal when the target is
unreachable, so a run never crashes the pipeline.
"""

from __future__ import annotations

import asyncio
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from sai_agents.agents.base import BaseAgent
from sai_agents.config import Settings, get_settings
from sai_agents.kafca.impact import score_impact
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import configure_logging, get_logger
from sai_agents.models import (
    AgentResult,
    EventType,
    FitnessScore,
    HealthResult,
    Insight,
    Recommendation,
    Severity,
)

log = get_logger("service_tester")


def probe_target(url: str, timeout: float = 10.0) -> HealthResult:
    """Perform a single blocking GET and return a typed HealthResult."""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "sai-agents-tester/0.1"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed scheme
            body = resp.read(4096)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return HealthResult(
                url=url,
                ok=200 <= resp.status < 400,
                status_code=resp.status,
                latency_ms=latency_ms,
                error=None if body is not None else "empty body",
            )
    except urllib.error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return HealthResult(url=url, ok=False, status_code=exc.code, latency_ms=latency_ms, error=str(exc))
    except Exception as exc:  # URLError, timeout, DNS, etc.
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return HealthResult(url=url, ok=False, status_code=None, latency_ms=latency_ms, error=str(exc))


def _fetch_headers(url: str, timeout: float) -> Dict[str, str]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "sai-agents-tester/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return {k.lower(): v for k, v in resp.headers.items()}
    except Exception:
        return {}


class ServiceTesterAgent(BaseAgent):
    name = "service_tester"
    event_type = EventType.EVOLUTION_SIGNAL

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        super().__init__(service=self.settings.service_name)
        self._probe = probe_target  # injectable for tests

    def run(self, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        context = context or {}
        url = context.get("target_url") or self.settings.target_url
        timeout = self.settings.target_timeout_seconds

        health = self._probe(url, timeout)
        insights: List[Insight] = []
        recommendations: List[Recommendation] = []

        if health.ok:
            insights.append(
                Insight(
                    title="Live site reachable",
                    detail=f"{url} responded {health.status_code} in {health.latency_ms} ms.",
                    severity=Severity.LOW,
                    impact_score=score_impact(Severity.LOW, confidence=0.9),
                    source_agent=self.name,
                    tags=["availability", "health"],
                )
            )
            # Latency-based UX signal.
            if health.latency_ms is not None and health.latency_ms > 1500:
                insights.append(
                    Insight(
                        title="Slow first response",
                        detail=f"First byte {health.latency_ms} ms > 1500 ms budget.",
                        severity=Severity.MEDIUM,
                        impact_score=score_impact(Severity.MEDIUM, confidence=0.7),
                        source_agent=self.name,
                        tags=["performance", "ux"],
                    )
                )
                recommendations.append(
                    Recommendation(
                        action="Enable edge caching / precompress assets on Netlify",
                        rationale="Sub-1.5s first response improves conversion and SEO.",
                        priority=Severity.MEDIUM,
                        impact_score=score_impact(Severity.MEDIUM, confidence=0.7),
                        effort="low",
                        source_agent=self.name,
                    )
                )
        else:
            insights.append(
                Insight(
                    title="Live site health check FAILED",
                    detail=f"{url} error: {health.error} (status={health.status_code}).",
                    severity=Severity.CRITICAL,
                    impact_score=score_impact(Severity.CRITICAL, confidence=0.95),
                    source_agent=self.name,
                    tags=["availability", "incident"],
                )
            )
            recommendations.append(
                Recommendation(
                    action="Investigate deploy / DNS / Netlify status immediately",
                    rationale="The public site is down or unreachable.",
                    priority=Severity.CRITICAL,
                    impact_score=score_impact(Severity.CRITICAL, confidence=0.95),
                    effort="high",
                    source_agent=self.name,
                )
            )

        fitness = self._fitness(health)
        return AgentResult(
            agent=self.name,
            ok=health.ok,
            insights=insights,
            recommendations=recommendations,
            fitness=fitness,
            payload={
                "health": health.model_dump(),
                "target_url": url,
            },
        )

    def _fitness(self, health: HealthResult) -> FitnessScore:
        """Compute a 0..1 deployment fitness for evo-metaclaw selection."""
        availability = 1.0 if health.ok else 0.0
        if health.latency_ms is None:
            latency = 0.0
        else:
            # 1.0 at 0ms, 0.0 at >=3000ms, linear.
            latency = max(0.0, min(1.0, 1.0 - health.latency_ms / 3000.0))
        components = {"availability": round(availability, 4), "latency": round(latency, 4)}
        score = round(0.7 * availability + 0.3 * latency, 4)
        return FitnessScore(
            genome="sai-agency-netlify-deploy",
            score=score,
            components=components,
            notes=f"status={health.status_code} latency_ms={health.latency_ms}",
        )

    # ------------------------------------------------------------------ #
    async def run_and_publish(
        self, publisher: Optional[KafkaEventPublisher] = None, context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """Run a probe and publish the resulting evolution signal to KafCa."""
        owns_publisher = publisher is None
        publisher = publisher or KafkaEventPublisher(self.settings)
        if owns_publisher:
            await publisher.start()
        try:
            result = self.execute(context)
            event = self.to_event(result)
            await publisher.publish(event)
            return result
        finally:
            if owns_publisher:
                await publisher.stop()


def main() -> None:
    """CLI entrypoint: probe the target once and publish the signal."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    agent = ServiceTesterAgent(settings)
    result = asyncio.run(agent.run_and_publish())
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
