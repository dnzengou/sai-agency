from sai_agents.kafca.impact import aggregate_impact, score_impact, severity_weight
from sai_agents.models import Insight, Recommendation, Severity


def test_score_bounds_and_monotonicity():
    low = score_impact(Severity.LOW, confidence=0.1, signal_count=1)
    high = score_impact(Severity.CRITICAL, confidence=1.0, signal_count=50)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_confidence_increases_score():
    a = score_impact(Severity.MEDIUM, confidence=0.2)
    b = score_impact(Severity.MEDIUM, confidence=0.9)
    assert b > a


def test_severity_weight_ordering():
    assert (
        severity_weight(Severity.LOW)
        < severity_weight(Severity.MEDIUM)
        < severity_weight(Severity.HIGH)
        < severity_weight(Severity.CRITICAL)
    )


def test_aggregate_empty_is_zero():
    assert aggregate_impact([], []) == 0.0


def test_aggregate_peak_weighting():
    insights = [
        Insight(title="noise", impact_score=0.1),
        Insight(title="critical", impact_score=1.0),
    ]
    agg = aggregate_impact(insights, [])
    # Peak-weighted: should sit well above the plain mean (0.55).
    assert agg > 0.6
    recs = [Recommendation(action="x", impact_score=0.5)]
    assert 0.0 <= aggregate_impact(insights, recs) <= 1.0
