"""ARM — Account & Relationship Management enrichment + impact scoring.

Turns a raw/normalised deal into an ARM-classified pipeline entry: assigns an
account, an ARM stage, an owner queue, a next action, and a priority derived
from a quantitative impact score. Deterministic and pure so it is testable and
reusable by evo-metaclaw fitness computations.
"""

from __future__ import annotations

import math
from typing import Optional

from sai_agents.models import ARMStage, Deal, DealType, Severity

# Which agent/owner queue picks up each deal type.
_OWNER_BY_TYPE = {
    DealType.FUNDING_ROUND: "sales_gtm",
    DealType.PARTNERSHIP: "sales_gtm",
    DealType.PUBLIC_TENDER: "sales_gtm",
    DealType.RFP: "sales_gtm",
    DealType.GRANT: "marketing",
    DealType.ACCELERATOR: "marketing",
    DealType.BUSINESS_SUCCESSION: "sales_gtm",  # a live buyer/seller match
    DealType.PROPERTY_SCHEME: "marketing",       # inbound relocation interest
    DealType.VENTURE: "sales_gtm",               # co-investment / venture vehicle
}

# Type weight — how directly actionable/valuable the type is for an agency.
_TYPE_WEIGHT = {
    DealType.RFP: 1.0,
    DealType.BUSINESS_SUCCESSION: 0.95,  # a concrete business/farm to take over
    DealType.PUBLIC_TENDER: 0.9,
    DealType.PARTNERSHIP: 0.85,
    DealType.PROPERTY_SCHEME: 0.8,       # a concrete relocation/property offer
    DealType.VENTURE: 0.75,              # co-investment / venture vehicle
    DealType.FUNDING_ROUND: 0.7,  # market signal / warm outreach
    DealType.GRANT: 0.6,
    DealType.ACCELERATOR: 0.5,
}

# Stage of the opportunity itself maps to an ARM pipeline stage.
_ARM_BY_STAGE = {
    "open": ARMStage.QUALIFIED,
    "upcoming": ARMStage.PROSPECT,
    "announced": ARMStage.PROSPECT,
    "closed": ARMStage.LOST,
}


def _value_factor(value_eur: Optional[float]) -> float:
    """Log-scaled 0..1 contribution of deal size (saturates for big rounds)."""
    if not value_eur or value_eur <= 0:
        return 0.3  # unknown value: neutral-low
    # ~0 at €10k, ~1 near €100M, smooth log scale.
    return max(0.0, min(1.0, (math.log10(value_eur) - 4.0) / 4.0))


def score_deal_impact(deal: Deal) -> float:
    """Blend type, value, confidence, and openness into a 0..1 impact score."""
    type_w = _TYPE_WEIGHT.get(deal.type, 0.6)
    value_w = _value_factor(deal.value_eur)
    openness = 1.0 if deal.stage in ("open", "upcoming", "announced") else 0.2
    raw = 0.4 * type_w + 0.3 * value_w + 0.2 * deal.confidence + 0.1 * openness
    return round(max(0.0, min(1.0, raw)), 4)


def _priority(impact: float) -> Severity:
    if impact >= 0.75:
        return Severity.CRITICAL
    if impact >= 0.6:
        return Severity.HIGH
    if impact >= 0.4:
        return Severity.MEDIUM
    return Severity.LOW


def _next_action(deal: Deal) -> str:
    if deal.type in (DealType.PUBLIC_TENDER, DealType.RFP):
        return f"Assess fit & prepare bid before {deal.deadline or 'the deadline'}"
    if deal.type == DealType.GRANT:
        return f"Check eligibility & draft application ({deal.deadline or 'rolling'})"
    if deal.type == DealType.ACCELERATOR:
        return "Evaluate cohort fit & submit expression of interest"
    if deal.type == DealType.FUNDING_ROUND:
        return f"Warm outreach to {deal.org} — post-raise AI/ML build needs"
    if deal.type == DealType.PROPERTY_SCHEME:
        return f"Register interest & check residency/renovation conditions ({deal.org})"
    if deal.type == DealType.BUSINESS_SUCCESSION:
        return f"Request the seller memorandum & arrange a viewing ({deal.org})"
    if deal.type == DealType.VENTURE:
        return f"Review the vehicle's thesis & ticket size ({deal.org})"
    return f"Open conversation with {deal.org}"


def classify_arm(deal: Deal) -> Deal:
    """Return the deal enriched with ARM fields + impact score (in place)."""
    deal.impact_score = score_deal_impact(deal)
    deal.priority = _priority(deal.impact_score)
    deal.owner = _OWNER_BY_TYPE.get(deal.type, "sales_gtm")
    deal.arm_stage = _ARM_BY_STAGE.get(deal.stage, ARMStage.PROSPECT)
    deal.account = deal.org or deal.title
    deal.next_action = _next_action(deal)
    return deal
