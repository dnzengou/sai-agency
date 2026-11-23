from sai_agents.evoforge import EvoForge, GenomeStats, stats_from_events
from sai_agents.evoforge.forge import SPEC_KNOBS, mutate
from sai_agents.models import EventType, EvolutionEvent, FitnessScore


def _ev(agent, impact, fitness=None):
    return EvolutionEvent(
        event_type=EventType.AGENT_RUN,
        source_agent=agent,
        impact_score=impact,
        fitness=(FitnessScore(genome=agent, score=fitness) if fitness is not None else None),
    )


def test_stats_from_events_blends_impact_and_fitness():
    events = [_ev("m", 0.8, 0.6), _ev("m", 0.9, 0.9), _ev("m", 0.2)]
    st = stats_from_events("m", events, high_watermark=0.7)
    assert st.events == 3
    assert st.mean_impact == round((0.8 + 0.9 + 0.2) / 3, 4)
    assert st.high_impact_rate == round(2 / 3, 4)  # 0.8 and 0.9 clear 0.7
    assert st.best_fitness == 0.9
    assert 0.0 <= st.score <= 1.0


def test_mutate_is_deterministic_and_clamped():
    spec = {k: 0.5 for k in SPEC_KNOBS}
    a = mutate(spec, "genomeX", 3, 0.2)
    b = mutate(spec, "genomeX", 3, 0.2)
    assert a == b  # deterministic for identical inputs
    assert mutate(spec, "genomeX", 4, 0.2) != a  # generation changes the noise
    assert all(0.0 <= v <= 1.0 for v in a.values())


def test_forge_accepts_better_candidate_and_persists(tmp_path):
    pop = tmp_path / "_population.json"
    forge = EvoForge(population_path=pop, mutation_rate=0.2)

    # Gen 1: first sighting establishes the champion baseline.
    r1 = forge.advance({"m": GenomeStats(genome="m", events=1, mean_impact=0.5, best_fitness=0.5)})
    assert r1.generation == 1
    assert forge.members["m"].best_score == 0.5
    assert pop.exists()

    # Gen 2: a higher score accepts the previously-proposed candidate.
    r2 = forge.advance({"m": GenomeStats(genome="m", events=2, mean_impact=0.9, best_fitness=0.9)})
    assert r2.accepted == 1 and r2.rejected == 0
    assert forge.members["m"].best_score >= 0.5
    assert r2.champion == "m"

    # Gen 3: a worse score rejects the candidate; champion best_score is retained.
    best_before = forge.members["m"].best_score
    r3 = forge.advance({"m": GenomeStats(genome="m", events=3, mean_impact=0.1, best_fitness=0.1)})
    assert r3.rejected == 1
    assert forge.members["m"].best_score == best_before


def test_forge_reloads_population_across_instances(tmp_path):
    pop = tmp_path / "_population.json"
    f1 = EvoForge(population_path=pop)
    f1.advance({"a": GenomeStats(genome="a", events=1, mean_impact=0.7, best_fitness=0.7)})
    gen1 = f1.generation

    f2 = EvoForge(population_path=pop)  # fresh instance, same file
    assert f2.generation == gen1
    assert "a" in f2.members
    assert f2.champion_specs()["a"] == f1.champion_specs()["a"]


def test_ranking_orders_by_best_score(tmp_path):
    forge = EvoForge(population_path=tmp_path / "p.json")
    report = forge.advance(
        {
            "lo": GenomeStats(genome="lo", events=1, mean_impact=0.2, best_fitness=0.2),
            "hi": GenomeStats(genome="hi", events=1, mean_impact=0.95, best_fitness=0.95),
        }
    )
    assert report.champion == "hi"
    assert [r["genome"] for r in report.ranking] == ["hi", "lo"]
