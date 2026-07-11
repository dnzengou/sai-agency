"""TrajectoryStore — durable, append-only JSONL trajectory persistence.

Design:
  * One JSONL file per genome under ``{root}/{genome}.jsonl``.
  * Every ``EvolutionEvent`` is one JSON line (schema-stable, replayable).
  * A companion ``_generations.jsonl`` records fitness bumps so evo-metaclaw
    can slice trajectories by generation without walking the full log.
  * Fail-safe: any I/O error is logged but never raised — a broken disk must
    not sink the live agents. This mirrors the KafCa `local-mode` fallback.
  * Thread-safe via a per-instance lock (the publisher runs across an asyncio
    loop + the ingest server's threading server).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterator, List, Optional

from sai_agents.logging_setup import get_logger
from sai_agents.models import EvolutionEvent, FitnessScore

log = get_logger("evometaclaw.trajectory")

_DEFAULT_ROOT_ENV = "SAI_TRAJECTORY_ROOT"
_DEFAULT_ENABLED_ENV = "SAI_TRAJECTORY_ENABLED"


def _default_root() -> Path:
    root = os.getenv(_DEFAULT_ROOT_ENV, "").strip()
    if root:
        return Path(root)
    return Path.home() / ".sai" / "trajectories"


class TrajectoryStore:
    """Append-only per-genome trajectory persistence for evo-metaclaw."""

    def __init__(self, root: Optional[Path | str] = None, enabled: Optional[bool] = None) -> None:
        self.root = Path(root) if root else _default_root()
        if enabled is None:
            raw = os.getenv(_DEFAULT_ENABLED_ENV, "true").strip().lower()
            enabled = raw in {"1", "true", "yes", "on"}
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._appended = 0
        self._genome_counts: dict[str, int] = {}
        if self.enabled:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning("trajectory.mkdir.failed", root=str(self.root), error=str(exc))
                self.enabled = False

    # ------------------------------------------------------------------ #
    @staticmethod
    def genome_of(event: EvolutionEvent) -> str:
        if event.fitness and event.fitness.genome:
            return event.fitness.genome
        return event.source_agent or "unknown"

    def _path_for(self, genome: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in genome)
        return self.root / f"{safe}.jsonl"

    def _generations_path(self, genome: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in genome)
        return self.root / f"{safe}._generations.jsonl"

    # ------------------------------------------------------------------ #
    def append(self, event: EvolutionEvent) -> bool:
        """Append one event. Returns True on write, False if disabled/erroring."""
        if not self.enabled:
            return False
        genome = self.genome_of(event)
        line = event.to_json() + "\n"
        try:
            with self._lock:
                with self._path_for(genome).open("a", encoding="utf-8") as fh:
                    fh.write(line)
                if event.fitness is not None:
                    self._record_generation(genome, event.fitness)
                self._appended += 1
                self._genome_counts[genome] = self._genome_counts.get(genome, 0) + 1
            return True
        except OSError as exc:
            log.warning("trajectory.append.failed", genome=genome, error=str(exc))
            return False

    def _record_generation(self, genome: str, fitness: FitnessScore) -> None:
        # Called under lock — safe to write the sibling generation log.
        entry = {
            "genome": fitness.genome or genome,
            "score": fitness.score,
            "components": fitness.components,
            "notes": fitness.notes,
        }
        try:
            with self._generations_path(genome).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            log.warning("trajectory.generation.failed", genome=genome, error=str(exc))

    # ------------------------------------------------------------------ #
    @property
    def total_appended(self) -> int:
        return self._appended

    def genome_count(self, genome: str) -> int:
        return self._genome_counts.get(genome, 0)

    def iter_trajectory(self, genome: str) -> Iterator[EvolutionEvent]:
        path = self._path_for(genome)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield EvolutionEvent(**json.loads(line))
                except Exception as exc:
                    log.warning("trajectory.read.parse", error=str(exc))

    def genomes(self) -> List[str]:
        if not self.enabled or not self.root.exists():
            return []
        return sorted(
            p.stem
            for p in self.root.glob("*.jsonl")
            if not p.stem.endswith("._generations")
        )
