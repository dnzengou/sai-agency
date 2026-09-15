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


# --------------------------------------------------------------------------- #
# Evolved ARM prioritisation — shared by the DealSourcingAgent (KafCa view) and
# the site generator (public deals.json order) so both rank deals identically.
# --------------------------------------------------------------------------- #
_NEUTRAL_SPEC = {
    "impact_bias": 0.5,
    "exploration": 0.5,
    "risk_tolerance": 0.5,
    "recency_weight": 0.5,
}


def skill_match(deal: Deal, loadout: set) -> float:
    """Fraction of the EvoSkillOpt loadout matched by the deal's attributes."""
    if not loadout:
        return 0.0
    attrs = {
        str(deal.region).lower(),
        str(deal.country).lower(),
        str(deal.type.value).lower(),
        str(deal.sector).lower(),
    }
    return len(attrs & loadout) / len(loadout)


def arm_rationale(deal: Deal, spec: Optional[dict] = None, loadout=None) -> list:
    """Short, human-legible reasons this deal ranks where it does.

    Explains the ARM priority to an end user in the deal card: which signals
    lifted it (actionable now, high impact, qualified, large ticket) and — when
    evolution is active — which learned focus skill it matches. Ordered by the
    same drivers ``arm_priority`` weights; capped to the top three.
    """
    loadout_set = {str(s).lower() for s in (loadout or [])}
    focus = ""
    if loadout_set:
        attrs = {
            str(deal.region).lower(),
            str(deal.country).lower(),
            str(deal.type.value).lower(),
            str(deal.sector).lower(),
        }
        matched = sorted(attrs & loadout_set)
        if matched:
            focus = "Focus: " + matched[0]
    # Ordered by how strongly each signal drives ARM priority; capped to three,
    # so the evolution "Focus" signal and a large ticket outrank the stage label.
    reasons: list = []
    if deal.stage in ("open", "upcoming"):
        reasons.append("Actionable now")
    if deal.impact_score >= 0.75:
        reasons.append("High impact")
    if focus:
        reasons.append(focus)
    if (deal.value_eur or 0) >= 1_000_000:
        reasons.append("Large ticket")
    if deal.arm_stage == ARMStage.QUALIFIED:
        reasons.append("Qualified")
    return reasons[:3]


def arm_priority(deal: Deal, spec: Optional[dict] = None, loadout=None) -> float:
    """Evolved ARM priority score for a deal (higher = surface sooner).

    With no evolution present (spec is None and no loadout) this is exactly the
    deal's impact score, so the pipeline's default order is unchanged and
    regeneration stays deterministic. When a champion spec / loadout is present,
    ``recency_weight`` tilts toward immediately actionable deals, ``impact_bias``
    toward open opportunities, and the loadout adds a skill-match bonus gated by
    ``exploration``. Deal impact scores themselves are never mutated — this is a
    separate ordering signal — so evolution reprioritises without gaming fitness.
    """
    loadout_set = {str(s).lower() for s in (loadout or [])}
    if spec is None and not loadout_set:
        return round(deal.impact_score, 4)
    s = spec or _NEUTRAL_SPEC
    rw = s.get("recency_weight", 0.5)
    ib = s.get("impact_bias", 0.5)
    ex = s.get("exploration", 0.5)
    actionable = 1.0 if deal.stage in ("open", "upcoming") else 0.4
    openness = 1.0 if deal.stage in ("open", "upcoming") else 0.0
    sm = skill_match(deal, loadout_set)
    return round(
        (1 - rw) * deal.impact_score + rw * actionable + 0.1 * ib * openness + 0.15 * ex * sm,
        4,
    )
