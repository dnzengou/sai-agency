from sai_agents.evoskillopt import EvoSkillOpt, skills_from_events
from sai_agents.evoskillopt.optimizer import SkillStat
from sai_agents.models import EventType, EvolutionEvent, Insight


def _ev(*insights):
    return EvolutionEvent(
        event_type=EventType.INSIGHT,
        source_agent="agent",
        insights=list(insights),
    )


def test_skillstat_incremental_mean_and_ucb():
    s = SkillStat(skill="seo")
    s.update(1.0)
    s.update(0.0)
    assert s.value == 0.5 and s.pulls == 2
    # An unpulled arm is infinitely attractive to UCB.
    assert SkillStat(skill="new").ucb(total_pulls=10) == float("inf")
    assert s.ucb(total_pulls=10) > s.value  # exploration bonus is positive


def test_skills_from_events_assigns_reward_per_tag():
    events = [
        _ev(Insight(title="a", impact_score=0.9, tags=["seo", "content"])),
        _ev(Insight(title="b", impact_score=0.1, tags=["seo"])),
    ]
    stats = skills_from_events(events)
    assert set(stats) == {"seo", "content"}
    assert stats["seo"].pulls == 2
    assert stats["seo"].value == 0.5  # (0.9 + 0.1)/2
    assert stats["content"].value == 0.9


def test_optimize_ranks_persists_and_reloads(tmp_path):
    path = tmp_path / "_skills.json"
    opt = EvoSkillOpt(skills_path=path, loadout_size=2)
    report = opt.optimize(
        [
            _ev(Insight(title="x", impact_score=0.9, tags=["pentest"])),
            _ev(Insight(title="y", impact_score=0.8, tags=["outreach"])),
            _ev(Insight(title="z", impact_score=0.2, tags=["cold-email"])),
        ]
    )
    assert report.distinct_skills == 3
    assert report.ranked[0]["skill"] == "pentest"  # highest value first
    assert len(report.loadout) == 2
    # weights are normalised across skills (rounded to 4dp, so allow slack)
    assert abs(sum(r["weight"] for r in report.ranked) - 1.0) < 1e-3
    assert path.exists()

    # A fresh instance reloads the accumulated table.
    opt2 = EvoSkillOpt(skills_path=path)
    assert "pentest" in opt2.stats
    assert opt2.stats["pentest"].pulls == 1


def test_ema_blend_grows_confidence(tmp_path):
    path = tmp_path / "_skills.json"
    opt = EvoSkillOpt(skills_path=path)
    opt.optimize([_ev(Insight(title="a", impact_score=1.0, tags=["seo"]))])
    opt.optimize([_ev(Insight(title="b", impact_score=0.0, tags=["seo"]))])
    # pulls accumulate across runs; value EMA-blends toward the new evidence.
    assert opt.stats["seo"].pulls == 2
    assert 0.0 < opt.stats["seo"].value < 1.0
