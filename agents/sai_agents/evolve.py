"""EvoFlywheel — consume accumulated trajectories, evolve, feed KafCa.

    python -m sai_agents.evolve

One turn of the flywheel:

    trajectories (EvoMetaClaw)
        │  read per-genome logs
        ▼
    EvoForge.advance()      → champion/candidate behavioural specs
    EvoSkillOpt.optimize()  → ranked skills + next loadout
        │  emit as EVOLUTION_SIGNAL (E + Im + Bl guarded)
        ▼
    KafCa publisher → trajectories …  (loop)

Everything is fail-safe and local-mode friendly: with no Kafka and an empty
trajectory root it simply reports an empty generation and exits 0, so it is
safe to run in CI as a smoke step.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from sai_agents.config import Settings, get_settings
from sai_agents.evoforge import EvoForge, GenomeStats, stats_from_events
from sai_agents.evometaclaw.trajectory import TrajectoryStore
from sai_agents.evoskillopt import EvoSkillOpt
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import configure_logging, get_logger
from sai_agents.models import EventType, EvolutionEvent, FitnessScore

log = get_logger("evolve")


class EvoFlywheel:
    """Reads trajectories, runs EvoForge + EvoSkillOpt, publishes signals."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        store: Optional[TrajectoryStore] = None,
        publisher: Optional[KafkaEventPublisher] = None,
        forge: Optional[EvoForge] = None,
        skillopt: Optional[EvoSkillOpt] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or TrajectoryStore()
        self.publisher = publisher or KafkaEventPublisher(self.settings)
        root = self.store.root
        self.forge = forge or EvoForge(
            population_path=root / "_population.json",
            high_watermark=self.settings.impact_high_watermark,
        )
        self.skillopt = skillopt or EvoSkillOpt(skills_path=root / "_skills.json")

    # ------------------------------------------------------------------ #
    def _read_trajectories(self):
        """Return (stats_by_genome, all_events). Excludes the forge's own
        lineages so evolution signals don't recursively drive selection."""
        stats: Dict[str, GenomeStats] = {}
        all_events: List[EvolutionEvent] = []
        wm = self.settings.impact_high_watermark
        for genome in self.store.genomes():
            if genome in ("evoforge", "evoskillopt"):
                continue
            events = list(self.store.iter_trajectory(genome))
            if not events:
                continue
            stats[genome] = stats_from_events(genome, events, high_watermark=wm)
            all_events.extend(events)
        return stats, all_events

    def _signals(self, forge_report, skill_report) -> List[EvolutionEvent]:
        events: List[EvolutionEvent] = []
        if forge_report.evaluated:
            events.append(
                EvolutionEvent(
                    event_type=EventType.EVOLUTION_SIGNAL,
                    service=self.settings.service_name,
                    source_agent="evoforge",
                    impact_score=forge_report.champion_score,
                    fitness=FitnessScore(
                        genome=forge_report.champion or "population",
                        score=forge_report.champion_score,
                        components={
                            "accepted": float(forge_report.accepted),
                            "rejected": float(forge_report.rejected),
                        },
                        notes=f"generation {forge_report.generation}",
                    ),
                    payload={
                        "generation": forge_report.generation,
                        "champion": forge_report.champion,
                        "ranking": forge_report.ranking[:5],
                        "candidates": self.forge.candidate_specs(),
                    },
                )
            )
        if skill_report.distinct_skills:
            top_value = skill_report.ranked[0]["value"] if skill_report.ranked else 0.0
            events.append(
                EvolutionEvent(
                    event_type=EventType.EVOLUTION_SIGNAL,
                    service=self.settings.service_name,
                    source_agent="evoskillopt",
                    impact_score=top_value,
                    payload={
                        "loadout": skill_report.loadout,
                        "explore": skill_report.explore,
                        "top_skills": skill_report.ranked[:8],
                        "total_pulls": skill_report.total_pulls,
                    },
                )
            )
        return events

    # ------------------------------------------------------------------ #
    async def turn(self) -> Dict:
        """Run one flywheel turn and return a compact summary."""
        stats, all_events = self._read_trajectories()
        forge_report = self.forge.advance(stats)
        skill_report = self.skillopt.optimize(all_events)

        signals = self._signals(forge_report, skill_report)
        await self.publisher.start()
        try:
            published = await self.publisher.publish_many(signals)
        finally:
            await self.publisher.stop()

        return {
            "generation": forge_report.generation,
            "genomes_evaluated": forge_report.evaluated,
            "accepted": forge_report.accepted,
            "rejected": forge_report.rejected,
            "champion": forge_report.champion,
            "champion_score": forge_report.champion_score,
            "distinct_skills": skill_report.distinct_skills,
            "skill_loadout": skill_report.loadout,
            "signals_published": published,
            "kafka_active": self.publisher.kafka_active,
        }


async def _run() -> Dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("evolve.start", trajectory_root=str(TrajectoryStore().root))
    return await EvoFlywheel(settings).turn()


def main() -> None:
    summary = asyncio.run(_run())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
