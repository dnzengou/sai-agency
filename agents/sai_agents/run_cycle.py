"""run_cycle — one self-compounding turn of the whole flywheel.

    python -m sai_agents.run_cycle

A single process that:
  1. Runs the full orchestrated team (KafCade + RRSS sourcing, ARM
     classification, all agents) — writing per-genome trajectories via KafCa.
  2. Turns the evolve flywheel (EvoForge + EvoSkillOpt) over those fresh
     trajectories — emitting champion specs + a skill loadout back onto KafCa.

Because the team loads the evolved champion specs at start-up and the flywheel
writes them at the end, running this on a schedule makes the population
*compound*: each cycle's agents inherit the previous cycle's champions. The
team and flywheel share one trajectory root (``SAI_TRAJECTORY_ROOT``), so the
evolve stage consumes exactly what the team just produced.
"""

from __future__ import annotations

import asyncio
import json

from sai_agents.config import get_settings
from sai_agents.evolve import EvoFlywheel
from sai_agents.evometaclaw.trajectory import TrajectoryStore
from sai_agents.logging_setup import configure_logging, get_logger
from sai_agents.orchestrator import OrchestratorTeam

log = get_logger("run_cycle")


async def _run() -> dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    root = TrajectoryStore().root
    log.info("run_cycle.start", trajectory_root=str(root), target=settings.target_url)

    # 1. Team run — writes trajectories (and consumes any existing champions).
    team = OrchestratorTeam(settings)
    team_summary = await team.run()

    # 2. Evolve — reads the trajectories just written, advances the population.
    evo_summary = await EvoFlywheel(settings).turn()

    return {
        "team": {
            "events_published": team_summary["events_published"],
            "team_fitness": team_summary["team_fitness"]["score"],
            "high_impact_events": team_summary["high_impact_events"],
            "evolved_genomes": team.evolved_specs and sorted(team.evolved_specs) or [],
            "skill_loadout_in": team.skill_loadout,
        },
        "evolve": evo_summary,
    }


def main() -> None:
    print(json.dumps(asyncio.run(_run()), indent=2))


if __name__ == "__main__":
    main()
