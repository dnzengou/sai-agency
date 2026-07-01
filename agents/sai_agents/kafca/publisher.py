"""KafkaEventPublisher — the KafCa event-sourcing spine.

Responsibilities:
  * Event Sourcing (E): append every EvolutionEvent to topic
    ``claw-evolution-events`` (append-only, replayable log).
  * Impact tracking (Im): stamp/propagate ``impact_score`` and surface high-
    impact events for evo-metaclaw prioritisation.
  * Bl: screen every event through the Blacklist and guard publishing with a
    Circuit Breaker so a broken Kafka (or a burst of unsafe input) cannot spin
    a bad evolution loop.

Design notes:
  * ``aiokafka`` is optional. When it is unavailable, or no bootstrap server is
    configured, the publisher falls back to structured local logging so the
    rest of the system keeps working (and events are never lost from the log).
  * Fully async, with graceful ``start`` / ``stop``.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from sai_agents.config import Settings, get_settings
from sai_agents.kafca.blacklist import Blacklist
from sai_agents.kafca.circuit_breaker import CircuitBreaker, CircuitOpenError
from sai_agents.logging_setup import get_logger
from sai_agents.models import EvolutionEvent

try:  # optional dependency
    from aiokafka import AIOKafkaProducer  # type: ignore

    _AIOKAFKA_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only where aiokafka absent
    AIOKafkaProducer = None  # type: ignore
    _AIOKAFKA_AVAILABLE = False

log = get_logger("kafca.publisher")


class KafkaEventPublisher:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        blacklist: Optional[Blacklist] = None,
        breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.blacklist = blacklist or Blacklist(
            extra_patterns=self.settings.blacklist_patterns
        )
        self.breaker = breaker or CircuitBreaker(
            failure_threshold=self.settings.breaker_failure_threshold,
            reset_seconds=self.settings.breaker_reset_seconds,
        )
        self._producer: Optional["AIOKafkaProducer"] = None
        self._started = False
        # In-process mirror of the event log — used for fallback + evo-metaclaw
        # consumers running in the same process, and for tests.
        self._local_log: List[EvolutionEvent] = []
        self._high_impact: List[EvolutionEvent] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def kafka_active(self) -> bool:
        return self._producer is not None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        if not (self.settings.kafka_enabled and self.settings.kafka_bootstrap_servers):
            log.info("kafca.start.local_mode", reason="kafka disabled or no bootstrap")
            return
        if not _AIOKAFKA_AVAILABLE:
            log.warning(
                "kafca.start.local_mode",
                reason="aiokafka not installed; install extra '[kafka]'",
            )
            return

        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                client_id=self.settings.kafka_client_id,
                enable_idempotence=True,
                acks="all",
            )
            await self._producer.start()
            log.info(
                "kafca.start.kafka_mode",
                bootstrap=self.settings.kafka_bootstrap_servers,
                topic=self.settings.kafka_topic,
            )
        except Exception as exc:  # pragma: no cover - needs a live broker
            self._producer = None
            log.error("kafca.start.failed", error=str(exc))

    async def stop(self) -> None:
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:  # pragma: no cover
                log.warning("kafca.stop.error", error=str(exc))
            finally:
                self._producer = None
        self._started = False
        log.info("kafca.stopped", published=len(self._local_log))

    async def __aenter__(self) -> "KafkaEventPublisher":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()

    # ------------------------------------------------------------------ #
    # Publishing
    # ------------------------------------------------------------------ #
    async def publish(self, event: EvolutionEvent) -> bool:
        """Publish one event. Returns True if it was accepted+sent (or locally
        durably logged), False if it was rejected (blacklist / breaker open).
        """
        # Bl: screen the event content before it can influence evolution.
        verdict = self._screen(event)
        if verdict.blocked:
            log.warning(
                "kafca.publish.blocked",
                event_type=event.event_type.value,
                source_agent=event.source_agent,
                matched=verdict.matched,
            )
            return False

        # Bl: circuit breaker gate.
        try:
            self.breaker.before_call()
        except CircuitOpenError as exc:
            log.error("kafca.publish.circuit_open", detail=str(exc))
            return False

        # Im: track high-impact events for evo-metaclaw prioritisation.
        if event.impact_score >= self.settings.impact_high_watermark:
            self._high_impact.append(event)

        try:
            await self._send(event)
        except Exception as exc:
            self.breaker.record_failure()
            log.error(
                "kafca.publish.failed",
                error=str(exc),
                breaker_state=self.breaker.state.value,
                failures=self.breaker.failures,
            )
            return False

        self.breaker.record_success()
        self._local_log.append(event)
        log.info(
            "kafca.publish.ok",
            event_id=event.event_id,
            event_type=event.event_type.value,
            source_agent=event.source_agent,
            impact_score=event.impact_score,
            transport="kafka" if self.kafka_active else "local",
        )
        return True

    async def publish_many(self, events: List[EvolutionEvent]) -> int:
        accepted = 0
        for event in events:
            if await self.publish(event):
                accepted += 1
        return accepted

    async def _send(self, event: EvolutionEvent) -> None:
        if self._producer is not None:
            await self._producer.send_and_wait(
                self.settings.kafka_topic,
                value=event.to_json().encode("utf-8"),
                key=event.kafka_key(),
            )
            return
        # Fallback: durable structured log line (event sourcing preserved).
        log.info("kafca.event", **_event_log_fields(event))

    def _screen(self, event: EvolutionEvent):
        texts: List[object] = [event.source_agent]
        for ins in event.insights:
            texts.extend([ins.title, ins.detail])
        for rec in event.recommendations:
            texts.extend([rec.action, rec.rationale])
        # Screen shallow payload string values too.
        for value in event.payload.values():
            if isinstance(value, str):
                texts.append(value)
        return self.blacklist.screen_many(texts)

    # ------------------------------------------------------------------ #
    # Read-side (event sourcing / evo-metaclaw consumption)
    # ------------------------------------------------------------------ #
    @property
    def event_log(self) -> List[EvolutionEvent]:
        """Append-only in-process view of published events."""
        return list(self._local_log)

    def high_impact_events(self) -> List[EvolutionEvent]:
        """Events at/above the high-impact watermark — evo-metaclaw feed."""
        return list(self._high_impact)


def _event_log_fields(event: EvolutionEvent) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "source_agent": event.source_agent,
        "impact_score": event.impact_score,
        "insights": len(event.insights),
        "recommendations": len(event.recommendations),
        "schema_version": event.schema_version,
    }
