from sai_agents.evo_report import build_report, _to_markdown, _plateaued
from sai_agents.evoforge import EvoForge, GenomeStats
from sai_agents.evoskillopt import EvoSkillOpt
from sai_agents.models import EventType, EvolutionEvent, Insight


def _ev(tag, impact):
    return EvolutionEvent(
        event_type=EventType.INSIGHT, source_agent="a",
        insights=[Insight(title="t", impact_score=impact, tags=[tag])],
    )


def test_build_report_ranks_and_flags(tmp_path):
    forge = EvoForge(population_path=tmp_path / "pop.json")
    forge.advance({
        "hi": GenomeStats(genome="hi", events=1, mean_impact=0.9, best_fitness=0.9),
        "lo": GenomeStats(genome="lo", events=1, mean_impact=0.3, best_fitness=0.3),
    })
    skill = EvoSkillOpt(skills_path=tmp_path / "sk.json")
    skill.optimize([_ev("seo", 0.9), _ev("latam", 0.4)])

    r = build_report(forge, skill)
    assert r["champion"] == "hi"
    assert r["genomes_tracked"] == 2
    assert [g["genome"] for g in r["ranking"]] == ["hi", "lo"]
    assert r["top_skills"][0]["skill"] == "seo"
    assert "seo" in r["loadout"]
    # markdown renders without error and contains the champion
    md = _to_markdown(r)
    assert "hi" in md and "Top skills" in md


def test_plateau_detection_flat_history(tmp_path):
    forge = EvoForge(population_path=tmp_path / "p.json")
    # Three near-identical scores across generations => plateaued.
    for _ in range(3):
        forge.advance({"g": GenomeStats(genome="g", events=1, mean_impact=0.50, best_fitness=0.50)})
    m = forge.members["g"]
    assert _plateaued(m) is True
    r = build_report(forge, EvoSkillOpt(skills_path=tmp_path / "s.json"))
    assert "g" in r["plateaued"]


def test_empty_report_is_safe(tmp_path):
    r = build_report(EvoForge(population_path=tmp_path / "p.json"), EvoSkillOpt(skills_path=tmp_path / "s.json"))
    assert r["genomes_tracked"] == 0 and r["champion"] is None
    assert r["ranking"] == [] and r["loadout"] == []
