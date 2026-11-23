import asyncio

from sai_agents.config import get_settings
from sai_agents.evolve import EvoFlywheel
from sai_agents.evometaclaw.trajectory import TrajectoryStore
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.models import EventType, EvolutionEvent, Insight


def _seed_store(root):
    store = TrajectoryStore(root=root, enabled=True)
    # Two agent lineages with differing impact + tagged insights.
    store.append(
        EvolutionEvent(
            event_type=EventType.INSIGHT,
            source_agent="marketing",
            impact_score=0.9,
            insights=[Insight(title="seo win", impact_score=0.9, tags=["seo", "content"])],
        )
    )
    store.append(
        EvolutionEvent(
            event_type=EventType.INSIGHT,
            source_agent="service_tester",
            impact_score=0.3,
            insights=[Insight(title="latency", impact_score=0.3, tags=["latency"])],
        )
    )
    return store


def test_flywheel_turn_evolves_and_publishes(tmp_path):
    root = tmp_path / "traj"
    store = _seed_store(root)
    # Publisher in local mode, writing its own signals into the same store.
    settings = get_settings()
    publisher = KafkaEventPublisher(settings, trajectory=store)
    wheel = EvoFlywheel(settings=settings, store=store, publisher=publisher)

    summary = asyncio.run(wheel.turn())

    assert summary["generation"] == 1
    assert summary["genomes_evaluated"] == 2  # marketing + service_tester
    assert summary["champion"] == "marketing"  # higher impact wins
    assert summary["distinct_skills"] == 3  # seo, content, latency
    assert summary["signals_published"] == 2  # evoforge + evoskillopt signals
    assert summary["skill_loadout"]  # non-empty
    # Persistence artifacts are written under the trajectory root.
    assert (root / "_population.json").exists()
    assert (root / "_skills.json").exists()


def test_flywheel_excludes_its_own_lineages(tmp_path):
    root = tmp_path / "traj"
    store = _seed_store(root)
    settings = get_settings()
    publisher = KafkaEventPublisher(settings, trajectory=store)
    wheel = EvoFlywheel(settings=settings, store=store, publisher=publisher)

    asyncio.run(wheel.turn())  # emits evoforge/evoskillopt signals into store
    # A second turn must still evaluate only the two agent lineages, never the
    # forge's own signals (no runaway self-reference).
    summary2 = asyncio.run(wheel.turn())
    assert summary2["genomes_evaluated"] == 2
    assert summary2["generation"] == 2


def test_flywheel_empty_trajectories_is_safe(tmp_path):
    root = tmp_path / "empty"
    store = TrajectoryStore(root=root, enabled=True)
    settings = get_settings()
    publisher = KafkaEventPublisher(settings, trajectory=store)
    wheel = EvoFlywheel(settings=settings, store=store, publisher=publisher)

    summary = asyncio.run(wheel.turn())
    assert summary["genomes_evaluated"] == 0
    assert summary["signals_published"] == 0
    assert summary["champion"] is None
