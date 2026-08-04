"""EvoSkillOpt internals — UCB1 bandit credit assignment over insight tags.

Determinism + fail-safe I/O match the rest of the KafCa stack: no random/time
seeds (UCB1 is a pure function of the accumulated counts/values), and skill
persistence degrades to in-memory on any disk error.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sai_agents.logging_setup import get_logger
from sai_agents.models import EvolutionEvent

log = get_logger("evoskillopt.optimizer")

# EMA weight for blending a re-optimisation pass into persisted history. New
# evidence counts, but the accumulated moat is not thrown away each run.
_EMA_ALPHA = 0.5


@dataclass
class SkillStat:
    """Bandit arm for one skill (insight tag)."""

    skill: str
    pulls: int = 0
    value: float = 0.0  # running mean reward in [0, 1]

    def update(self, reward: float) -> None:
        self.pulls += 1
        # Incremental mean.
        self.value += (reward - self.value) / self.pulls

    def ucb(self, total_pulls: int, c: float = 1.4142) -> float:
        if self.pulls == 0:
            return float("inf")
        return self.value + c * math.sqrt(math.log(max(1, total_pulls)) / self.pulls)

    def to_dict(self) -> dict:
        return {"skill": self.skill, "pulls": self.pulls, "value": round(self.value, 6)}

    @classmethod
    def from_dict(cls, d: dict) -> "SkillStat":
        return cls(skill=d["skill"], pulls=int(d.get("pulls", 0)), value=float(d.get("value", 0.0)))


def skills_from_events(events: Iterable[EvolutionEvent]) -> Dict[str, SkillStat]:
    """Fresh credit-assignment pass over a batch of events (no persistence)."""
    stats: Dict[str, SkillStat] = {}
    for e in events:
        for ins in e.insights:
            reward = ins.impact_score
            for tag in ins.tags:
                tag = (tag or "").strip().lower()
                if not tag:
                    continue
                stats.setdefault(tag, SkillStat(skill=tag)).update(reward)
    return stats


@dataclass
class SkillReport:
    total_pulls: int
    distinct_skills: int
    ranked: List[dict]  # [{skill, value, pulls, ucb, weight}]
    loadout: List[str]  # top-N skills worth exercising next (by UCB)
    explore: List[str]  # under-sampled skills UCB wants to try


class EvoSkillOpt:
    """Persistent UCB1 skill optimiser."""

    def __init__(
        self,
        skills_path: Optional[Path | str] = None,
        loadout_size: int = 5,
        explore_c: float = 1.4142,
    ) -> None:
        self.skills_path = Path(skills_path) if skills_path else None
        self.loadout_size = loadout_size
        self.explore_c = explore_c
        self.stats: Dict[str, SkillStat] = {}
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.skills_path or not self.skills_path.exists():
            return
        try:
            data = json.loads(self.skills_path.read_text(encoding="utf-8"))
            for sd in data.get("skills", []):
                s = SkillStat.from_dict(sd)
                self.stats[s.skill] = s
        except (OSError, ValueError, KeyError) as exc:
            log.warning("evoskillopt.load.failed", path=str(self.skills_path), error=str(exc))

    def _save(self) -> None:
        if not self.skills_path:
            return
        payload = {"skills": [s.to_dict() for s in self.stats.values()]}
        try:
            self.skills_path.parent.mkdir(parents=True, exist_ok=True)
            self.skills_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("evoskillopt.save.failed", path=str(self.skills_path), error=str(exc))

    # ------------------------------------------------------------------ #
    def optimize(self, events: Iterable[EvolutionEvent]) -> SkillReport:
        """Fold a batch of events into the persistent skill table and rank."""
        batch = skills_from_events(events)
        for skill, fresh in batch.items():
            prior = self.stats.get(skill)
            if prior is None:
                self.stats[skill] = fresh
            else:
                # EMA-blend the fresh mean into the accumulated value; sum pulls
                # so confidence (and UCB's exploration term) keeps growing.
                prior.value = round((1 - _EMA_ALPHA) * prior.value + _EMA_ALPHA * fresh.value, 6)
                prior.pulls += fresh.pulls
        self._save()

        total_pulls = sum(s.pulls for s in self.stats.values())
        rows = []
        for s in self.stats.values():
            ucb = s.ucb(total_pulls, self.explore_c)
            rows.append(
                {
                    "skill": s.skill,
                    "value": round(s.value, 4),
                    "pulls": s.pulls,
                    "ucb": (None if math.isinf(ucb) else round(ucb, 4)),
                }
            )
        # Normalised exploit weights (by value) for a downstream consumer.
        value_sum = sum(r["value"] for r in rows) or 1.0
        for r in rows:
            r["weight"] = round(r["value"] / value_sum, 4)

        by_value = sorted(rows, key=lambda r: r["value"], reverse=True)
        # UCB ranking: unpulled (inf) first, then by ucb desc.
        by_ucb = sorted(rows, key=lambda r: (r["ucb"] is None, r["ucb"] or 0.0), reverse=True)
        explore = [r["skill"] for r in rows if r["pulls"] <= 1]

        report = SkillReport(
            total_pulls=total_pulls,
            distinct_skills=len(self.stats),
            ranked=by_value,
            loadout=[r["skill"] for r in by_ucb[: self.loadout_size]],
            explore=explore[: self.loadout_size],
        )
        log.info(
            "evoskillopt.optimized",
            distinct_skills=report.distinct_skills,
            total_pulls=total_pulls,
            loadout=report.loadout,
        )
        return report
