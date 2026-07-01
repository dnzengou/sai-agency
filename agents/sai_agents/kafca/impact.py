"""Impact tracking (Im) — quantify how much an event should influence
evo-metaclaw evolution.

The score is a bounded weighted blend of severity, agent confidence, and signal
density. Deterministic and side-effect free so it can be unit-tested and reused
by any agent.
"""

from __future__ import annotations

from typing import Sequence

from sai_agents.models import Insight, Recommendation, Severity

_SEVERITY_WEIGHT = {
    Severity.LOW: 0.25,
    Severity.MEDIUM: 0.5,
    Severity.HIGH: 0.8,
    Severity.CRITICAL: 1.0,
}


def severity_weight(severity: Severity) -> float:
    return _SEVERITY_WEIGHT.get(severity, 0.5)


def score_impact(
    severity: Severity = Severity.MEDIUM,
    confidence: float = 0.5,
    signal_count: int = 1,
) -> float:
    """Blend severity, confidence, and signal density into a 0..1 impact score.

    - severity: how bad/important the finding is.
    - confidence: 0..1, how sure the agent is.
    - signal_count: number of corroborating signals; saturating contribution.
    """
    confidence = max(0.0, min(1.0, confidence))
    sev = severity_weight(severity)
    # Density saturates: 1 signal -> 0, ~many signals -> ~1, via 1 - 1/(1+n).
    density = 1.0 - 1.0 / (1.0 + max(0, signal_count))
    raw = 0.55 * sev + 0.30 * confidence + 0.15 * density
    return round(max(0.0, min(1.0, raw)), 4)


def aggregate_impact(
    insights: Sequence[Insight] = (),
    recommendations: Sequence[Recommendation] = (),
) -> float:
    """Aggregate impact across an event's insights + recommendations.

    Uses the max (worst-case) blended with the mean so a single critical signal
    is never diluted by noise, while breadth still counts.
    """
    scores = [i.impact_score for i in insights] + [
        r.impact_score for r in recommendations
    ]
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    peak = max(scores)
    return round(0.6 * peak + 0.4 * mean, 4)
