"""EvoForge internals — GenomeStats, GenomeSpec, and the (1+1)-ES forge loop.

Design goals, mirroring the rest of the KafCa stack:
  * Deterministic. Mutation noise is derived by hashing (genome, generation,
    knob) so a given trajectory + generation always yields the same candidate.
    No ``random``/time seeds — evolution must be replayable for evo-metaclaw.
  * Fail-safe I/O. Population persistence never raises into the caller; a
    broken disk degrades to an in-memory population, exactly like
    ``TrajectoryStore``.
  * Additive + self-contained. Consumes ``EvolutionEvent`` trajectories and
    emits ``GenomeSpec`` recommendations; it does not reach into the agents.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sai_agents.logging_setup import get_logger
from sai_agents.models import EvolutionEvent

log = get_logger("evoforge.forge")

# The evolvable behavioural knobs. Each is a weight in [0, 1] that a downstream
# agent may consume to bias its behaviour. Kept small and named so the evolved
# champion specs are human-legible.
SPEC_KNOBS = ("impact_bias", "exploration", "risk_tolerance", "recency_weight")

_DEFAULT_SPEC = {k: 0.5 for k in SPEC_KNOBS}

_HISTORY_CAP = 24  # keep the score history bounded on disk


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


# --------------------------------------------------------------------------- #
# Fitness derivation
# --------------------------------------------------------------------------- #
@dataclass
class GenomeStats:
    """Fitness signal derived from a single genome's trajectory."""

    genome: str
    events: int = 0
    mean_impact: float = 0.0
    high_impact_rate: float = 0.0
    best_fitness: float = 0.0
    last_fitness: float = 0.0
    fitness_trend: float = 0.0  # last - first observed fitness score

    @property
    def score(self) -> float:
        """Blended selection score in [0, 1].

        Uses observed genome fitness where available (best + latest), and always
        folds in the impact signal so genomes with no explicit FitnessScore
        (most agent lineages) still get a meaningful, comparable score.
        """
        base = 0.5 * self.best_fitness + 0.5 * self.mean_impact
        # A small bonus for a high high-impact rate and positive momentum.
        base += 0.1 * self.high_impact_rate + 0.1 * max(0.0, self.fitness_trend)
        return round(_clamp01(base), 4)


def stats_from_events(
    genome: str,
    events: Iterable[EvolutionEvent],
    high_watermark: float = 0.7,
) -> GenomeStats:
    """Fold a genome's trajectory into a GenomeStats."""
    n = 0
    impact_sum = 0.0
    high = 0
    fitness_scores: List[float] = []
    for e in events:
        n += 1
        impact_sum += e.impact_score
        if e.impact_score >= high_watermark:
            high += 1
        if e.fitness is not None:
            fitness_scores.append(e.fitness.score)
    if n == 0:
        return GenomeStats(genome=genome)
    best = max(fitness_scores) if fitness_scores else round(impact_sum / n, 4)
    last = fitness_scores[-1] if fitness_scores else round(impact_sum / n, 4)
    trend = round(last - fitness_scores[0], 4) if len(fitness_scores) >= 2 else 0.0
    return GenomeStats(
        genome=genome,
        events=n,
        mean_impact=round(impact_sum / n, 4),
        high_impact_rate=round(high / n, 4),
        best_fitness=round(best, 4),
        last_fitness=round(last, 4),
        fitness_trend=trend,
    )


# --------------------------------------------------------------------------- #
# Specs & population members
# --------------------------------------------------------------------------- #
GenomeSpec = Dict[str, float]


def default_spec() -> GenomeSpec:
    return dict(_DEFAULT_SPEC)


def _spec_noise(genome: str, generation: int, knob: str) -> float:
    """Deterministic noise in [-1, 1] for a (genome, generation, knob)."""
    seed = f"{genome}|{generation}|{knob}".encode("utf-8")
    h = int(hashlib.sha1(seed).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF) * 2.0 - 1.0


def mutate(spec: GenomeSpec, genome: str, generation: int, rate: float) -> GenomeSpec:
    """Propose a mutated candidate spec (deterministic per inputs)."""
    return {
        knob: round(_clamp01(spec.get(knob, 0.5) + _spec_noise(genome, generation, knob) * rate), 4)
        for knob in SPEC_KNOBS
    }


@dataclass
class PopulationMember:
    """One genome's evolving lineage: champion spec + proposed candidate."""

    genome: str
    spec: GenomeSpec = field(default_factory=default_spec)
    candidate: GenomeSpec = field(default_factory=default_spec)
    best_score: float = 0.0
    last_score: float = 0.0
    generation: int = 0
    accepts: int = 0
    rejects: int = 0
    history: List[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "genome": self.genome,
            "spec": self.spec,
            "candidate": self.candidate,
            "best_score": self.best_score,
            "last_score": self.last_score,
            "generation": self.generation,
            "accepts": self.accepts,
            "rejects": self.rejects,
            "history": self.history[-_HISTORY_CAP:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PopulationMember":
        return cls(
            genome=d["genome"],
            spec={k: float(d.get("spec", {}).get(k, 0.5)) for k in SPEC_KNOBS},
            candidate={k: float(d.get("candidate", {}).get(k, 0.5)) for k in SPEC_KNOBS},
            best_score=float(d.get("best_score", 0.0)),
            last_score=float(d.get("last_score", 0.0)),
            generation=int(d.get("generation", 0)),
            accepts=int(d.get("accepts", 0)),
            rejects=int(d.get("rejects", 0)),
            history=[float(x) for x in d.get("history", [])][-_HISTORY_CAP:],
        )


@dataclass
class ForgeReport:
    generation: int
    evaluated: int
    accepted: int
    rejected: int
    champion: Optional[str]
    champion_score: float
    ranking: List[dict]  # [{genome, score, best_score, spec}]


# --------------------------------------------------------------------------- #
# The forge
# --------------------------------------------------------------------------- #
class EvoForge:
    """(1+1)-ES over per-genome behavioural specs, driven by trajectory fitness.

    Each ``advance`` is one generation:
      1. For every genome with fresh stats, compare its current score against
         the champion's ``best_score``. If the last-proposed candidate did at
         least as well, *accept* it as the new champion; otherwise *reject* and
         keep the champion.
      2. Propose a new mutated candidate for the next generation.
      3. Persist the population and return a ranked report.
    """

    def __init__(
        self,
        population_path: Optional[Path | str] = None,
        mutation_rate: float = 0.2,
        high_watermark: float = 0.7,
    ) -> None:
        self.population_path = Path(population_path) if population_path else None
        self.mutation_rate = mutation_rate
        self.high_watermark = high_watermark
        self.generation = 0
        self.members: Dict[str, PopulationMember] = {}
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.population_path or not self.population_path.exists():
            return
        try:
            data = json.loads(self.population_path.read_text(encoding="utf-8"))
            self.generation = int(data.get("generation", 0))
            for md in data.get("members", []):
                m = PopulationMember.from_dict(md)
                self.members[m.genome] = m
        except (OSError, ValueError, KeyError) as exc:
            log.warning("evoforge.load.failed", path=str(self.population_path), error=str(exc))

    def _save(self) -> None:
        if not self.population_path:
            return
        payload = {
            "generation": self.generation,
            "members": [m.to_dict() for m in self.members.values()],
        }
        try:
            self.population_path.parent.mkdir(parents=True, exist_ok=True)
            self.population_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("evoforge.save.failed", path=str(self.population_path), error=str(exc))

    # ------------------------------------------------------------------ #
    def advance(self, stats_by_genome: Dict[str, GenomeStats]) -> ForgeReport:
        """Run one generation of selection + mutation over the given stats."""
        gen = self.generation
        accepted = rejected = 0
        for genome, stats in stats_by_genome.items():
            score = stats.score
            m = self.members.get(genome)
            if m is None:
                # First sighting: the default spec becomes the champion baseline.
                m = PopulationMember(genome=genome, best_score=score, last_score=score)
                m.history.append(score)
                self.members[genome] = m
            else:
                # (1+1)-ES accept/reject of the previously-proposed candidate.
                if score >= m.best_score:
                    m.spec = dict(m.candidate)
                    m.best_score = score
                    m.accepts += 1
                    accepted += 1
                else:
                    m.rejects += 1
                    rejected += 1
                m.last_score = score
                m.history.append(score)
            # Propose the next candidate to be exercised next generation.
            m.candidate = mutate(m.spec, genome, gen + 1, self.mutation_rate)
            m.generation = gen + 1

        self.generation = gen + 1
        self._save()

        ranking = sorted(
            (
                {
                    "genome": m.genome,
                    "score": m.last_score,
                    "best_score": m.best_score,
                    "spec": m.spec,
                }
                for m in self.members.values()
            ),
            key=lambda r: r["best_score"],
            reverse=True,
        )
        champ = ranking[0] if ranking else None
        report = ForgeReport(
            generation=self.generation,
            evaluated=len(stats_by_genome),
            accepted=accepted,
            rejected=rejected,
            champion=champ["genome"] if champ else None,
            champion_score=champ["best_score"] if champ else 0.0,
            ranking=ranking,
        )
        log.info(
            "evoforge.advanced",
            generation=self.generation,
            evaluated=report.evaluated,
            accepted=accepted,
            rejected=rejected,
            champion=report.champion,
        )
        return report

    # ------------------------------------------------------------------ #
    def champion_specs(self) -> Dict[str, GenomeSpec]:
        """The current best spec per genome — the tunable an agent consumes."""
        return {g: dict(m.spec) for g, m in self.members.items()}

    def candidate_specs(self) -> Dict[str, GenomeSpec]:
        """The next spec to exercise per genome (what to run this generation)."""
        return {g: dict(m.candidate) for g, m in self.members.items()}
