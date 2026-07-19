"""Typed domain models — the evolution-grade signals for evo-metaclaw.

Every artifact an agent produces is a validated pydantic model so downstream
consumers (``evo-metaclaw`` / ``evolved-skill-opt`` population-based evolution)
get clean, schema-stable input. Nothing leaves an agent untyped.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(str, Enum):
    """Categories of events published to the KafCa event stream."""

    HEALTH_CHECK = "health_check"
    FEEDBACK = "feedback"
    INSIGHT = "insight"
    RECOMMENDATION = "recommendation"
    EVOLUTION_SIGNAL = "evolution_signal"
    SECURITY_FINDING = "security_finding"
    AGENT_RUN = "agent_run"
    DEAL_SIGNAL = "deal_signal"
    LEAD_SIGNAL = "lead_signal"  # emitted by the Netlify lead-bridge function
    MATCH_SIGNAL = "match_signal"  # emitted by the Matchmaking agent


class Insight(BaseModel):
    """A single actionable observation produced by an agent."""

    id: str = Field(default_factory=_new_id)
    title: str
    detail: str = ""
    severity: Severity = Severity.MEDIUM
    # 0.0 (noise) .. 1.0 (mission-critical). Drives evolution prioritisation.
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_agent: str = "unknown"
    tags: List[str] = Field(default_factory=list)

    @field_validator("impact_score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class Recommendation(BaseModel):
    """A concrete, prioritised action derived from insights."""

    id: str = Field(default_factory=_new_id)
    action: str
    rationale: str = ""
    priority: Severity = Severity.MEDIUM
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)
    effort: str = "medium"  # low | medium | high
    source_agent: str = "unknown"


class FitnessScore(BaseModel):
    """A genome/skill fitness measure for evo-metaclaw selection pressure."""

    genome: str
    score: float = Field(ge=0.0, le=1.0)
    components: Dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class EvolutionEvent(BaseModel):
    """Canonical envelope published to Kafka topic ``claw-evolution-events``.

    This is the contract with evo-metaclaw. Keep it additive and backwards
    compatible — new fields ok, never repurpose or remove existing ones.
    """

    event_id: str = Field(default_factory=_new_id)
    event_type: EventType
    timestamp: str = Field(default_factory=_utcnow_iso)
    service: str = "sai-agents"
    source_agent: str = "unknown"
    # Aggregate impact of the whole event (0..1). High-impact events are
    # prioritised for evo-metaclaw evolution.
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)
    schema_version: int = 1
    payload: Dict[str, Any] = Field(default_factory=dict)
    insights: List[Insight] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    fitness: Optional[FitnessScore] = None

    @field_validator("impact_score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    def kafka_key(self) -> bytes:
        """Partition key — keep per-agent ordering in the topic."""
        return self.source_agent.encode("utf-8")

    def to_json(self) -> str:
        return self.model_dump_json()


class DealType(str, Enum):
    GRANT = "grant"
    PUBLIC_TENDER = "public_tender"
    ACCELERATOR = "accelerator"
    FUNDING_ROUND = "funding_round"
    PARTNERSHIP = "partnership"
    RFP = "rfp"
    # Succession & repopulation theme (property + ventures perspective)
    PROPERTY_SCHEME = "property_scheme"        # €1 houses, relocation/settler schemes
    BUSINESS_SUCCESSION = "business_succession"  # business/farm seeking a successor
    VENTURE = "venture"                          # rural venture / co-investment vehicle


class DealCategory(str, Enum):
    """Top-level opportunity family — powers the demo/thematic views."""

    AI_ML = "ai_ml"                # AI/ML/data grants, tenders, rounds (default)
    REPOPULATION = "repopulation"  # emptying-village / €1-house / relocation schemes
    SUCCESSION = "succession"      # ageing owners seeking a successor/buyer
    VENTURE = "venture"            # rural ventures / mixed opportunities


class ARMStage(str, Enum):
    """Account & Relationship Management pipeline stage."""

    PROSPECT = "prospect"
    QUALIFIED = "qualified"
    ENGAGED = "engaged"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"


class Deal(BaseModel):
    """A sourced real-world opportunity, ARM-classified for the pipeline view."""

    id: str = Field(default_factory=_new_id)
    title: str
    org: str = ""
    country: str = ""
    region: str = ""  # "Southern Europe" | "Nordics"
    city: Optional[str] = None
    sector: str = ""
    type: DealType = DealType.GRANT
    category: DealCategory = DealCategory.AI_ML
    value_eur: Optional[float] = None
    stage: str = "open"  # open | upcoming | closed | announced
    deadline: Optional[str] = None
    date: Optional[str] = None
    source_url: str = ""
    source_name: str = ""
    description: str = ""
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    # --- ARM (Account & Relationship Management) enrichment ---
    account: str = ""
    arm_stage: ARMStage = ARMStage.PROSPECT
    owner: str = "unassigned"
    next_action: str = ""
    priority: Severity = Severity.MEDIUM
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)

    def dedupe_key(self) -> str:
        return f"{self.title.strip().lower()}|{self.org.strip().lower()}|{self.country.strip().lower()}"


class HealthResult(BaseModel):
    """Outcome of probing a live target (e.g. sai-agency.netlify.app)."""

    url: str
    ok: bool
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    checked_at: str = Field(default_factory=_utcnow_iso)


class AgentResult(BaseModel):
    """Uniform return type for every agent run."""

    agent: str
    ok: bool = True
    insights: List[Insight] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    fitness: Optional[FitnessScore] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    @property
    def aggregate_impact(self) -> float:
        scores = [i.impact_score for i in self.insights] + [
            r.impact_score for r in self.recommendations
        ]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)
