import asyncio

from sai_agents.deals.deal_sourcing_agent import DealSourcingAgent
from sai_agents.models import Deal, DealType


def _deal(title, impact, stage, dtype="grant"):
    d = Deal(
        title=title,
        org="Org",
        type=DealType(dtype),
        country="Spain",
        region="Southern Europe",
        sector="AI/ML",
        stage=stage,
    )
    d.impact_score = impact
    return d


def test_arm_rank_is_noop_without_spec():
    agent = DealSourcingAgent()  # spec is None
    deals = [_deal("a", 0.9, "closed"), _deal("b", 0.5, "open")]
    assert agent._arm_rank(deals) == deals  # unchanged order (impact order)


def test_arm_rank_recency_promotes_actionable_deals():
    # High recency_weight should lift an open deal above a higher-impact closed one.
    agent = DealSourcingAgent(spec={"recency_weight": 0.9, "impact_bias": 0.5})
    closed_hi = _deal("closed-hi", 0.85, "closed")
    open_lo = _deal("open-lo", 0.55, "open")
    ranked = agent._arm_rank([closed_hi, open_lo])
    assert ranked[0].title == "open-lo"  # actionability wins under high recency


def test_arm_rank_low_recency_keeps_impact_order():
    agent = DealSourcingAgent(spec={"recency_weight": 0.0, "impact_bias": 0.5})
    closed_hi = _deal("closed-hi", 0.85, "closed")
    open_lo = _deal("open-lo", 0.55, "open")
    ranked = agent._arm_rank([closed_hi, open_lo])
    assert ranked[0].title == "closed-hi"  # pure impact when recency weight is 0


def test_run_cycle_end_to_end(tmp_path, monkeypatch):
    # A full cycle writes trajectories then evolves; on a fresh root the team
    # starts unevolved and the flywheel produces a first generation.
    monkeypatch.setenv("SAI_TRAJECTORY_ROOT", str(tmp_path / "traj"))
    monkeypatch.setenv("SAI_TARGET_URL", "https://example.test")
    monkeypatch.setenv("KAFKA_ENABLED", "false")
    # get_settings is cached; import inside so the env is read fresh.
    from sai_agents.config import get_settings

    get_settings.cache_clear()
    from sai_agents.run_cycle import _run

    summary = asyncio.run(_run())
    assert summary["team"]["events_published"] == 7
    assert summary["evolve"]["generation"] == 1
    assert summary["evolve"]["genomes_evaluated"] >= 5  # the agent lineages
    assert (tmp_path / "traj" / "_population.json").exists()
    get_settings.cache_clear()
