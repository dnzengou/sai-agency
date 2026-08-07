"""EvoForge — population-based evolution over accumulated trajectories.

EvoMetaClaw accumulates the data (per-genome JSONL trajectories). EvoForge is
the *selection pressure* that consumes it: it reads each genome's trajectory,
derives a fitness signal, and runs a deterministic (1+1)-ES hill-climber that
maintains a champion behavioural ``GenomeSpec`` per genome and proposes a
mutated candidate for the next generation.

The champion specs are the forge's output: a downstream agent can read
``EvoForge.champion_specs()`` to tune its behaviour, and each proposed candidate
is emitted as an ``EVOLUTION_SIGNAL`` back onto the KafCa stream — closing the
flywheel (run → trajectory → forge → signal → run).
"""

from sai_agents.evoforge.forge import (
    EvoForge,
    ForgeReport,
    GenomeSpec,
    GenomeStats,
    PopulationMember,
    stats_from_events,
)

__all__ = [
    "EvoForge",
    "ForgeReport",
    "GenomeSpec",
    "GenomeStats",
    "PopulationMember",
    "stats_from_events",
]
