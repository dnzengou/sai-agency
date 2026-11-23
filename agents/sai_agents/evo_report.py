"""evo_report — make the flywheel's progress legible.

    python -m sai_agents.evo_report            # JSON report
    python -m sai_agents.evo_report --markdown # Markdown snapshot

Reads the accumulated EvoForge population + EvoSkillOpt skill table and
summarises how evolution is going: per-genome generation, best/last score,
score trend, accept/reject ratio, a plateau flag, the reigning champion, and
the top-valued skills. No live run — pure read over the trajectory store, so it
is safe to call any time (and from the evo-cycle) to observe the flywheel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

from sai_agents.config import get_settings
from sai_agents.evoforge import EvoForge
from sai_agents.evometaclaw.trajectory import TrajectoryStore
from sai_agents.evoskillopt import EvoSkillOpt
from sai_agents.logging_setup import get_logger

log = get_logger("evo_report")

# A genome has plateaued if its recent scores are flat (no improvement beyond
# epsilon) across this many generations, or it keeps rejecting candidates.
_PLATEAU_WINDOW = 3
_PLATEAU_EPS = 0.01


def _plateaued(member) -> bool:
    hist = member.history[-_PLATEAU_WINDOW:]
    if len(hist) >= _PLATEAU_WINDOW and (max(hist) - min(hist)) <= _PLATEAU_EPS:
        return True
    # Many more rejects than accepts once a few generations deep.
    if member.generation >= _PLATEAU_WINDOW and member.rejects >= 2 * max(1, member.accepts):
        return True
    return False


def build_report(forge: EvoForge, skillopt: EvoSkillOpt, trajectory: Optional[TrajectoryStore] = None) -> Dict:
    """Pure summary of the current evolution state (testable without disk)."""
    genomes = []
    for m in forge.members.values():
        trials = m.accepts + m.rejects
        hist = m.history
        genomes.append(
            {
                "genome": m.genome,
                "generation": m.generation,
                "best_score": round(m.best_score, 4),
                "last_score": round(m.last_score, 4),
                "trend": round((hist[-1] - hist[0]), 4) if len(hist) >= 2 else 0.0,
                "accept_rate": round(m.accepts / trials, 4) if trials else 0.0,
                "accepts": m.accepts,
                "rejects": m.rejects,
                "plateaued": _plateaued(m),
                "spec": m.spec,
            }
        )
    genomes.sort(key=lambda g: g["best_score"], reverse=True)

    skills = sorted(
        ({"skill": s.skill, "value": round(s.value, 4), "pulls": s.pulls} for s in skillopt.stats.values()),
        key=lambda s: s["value"],
        reverse=True,
    )

    champion = genomes[0] if genomes else None
    return {
        "generation": forge.generation,
        "genomes_tracked": len(genomes),
        "champion": champion["genome"] if champion else None,
        "champion_score": champion["best_score"] if champion else 0.0,
        "plateaued": [g["genome"] for g in genomes if g["plateaued"]],
        "ranking": genomes,
        "top_skills": skills[:10],
        "loadout": skillopt.current_loadout(5),
        # EvoMetaClaw moat: how much durable trajectory data has accumulated.
        "trajectory": trajectory.accumulation() if trajectory is not None else None,
    }


def _to_markdown(r: Dict) -> str:
    lines = [
        "# EvoMetaClaw — evolution report",
        "",
        f"- Generation: **{r['generation']}**",
        f"- Champion: **{r['champion'] or '—'}** ({r['champion_score']})",
        f"- Genomes tracked: {r['genomes_tracked']}",
        f"- Plateaued: {', '.join(r['plateaued']) or 'none'}",
        "",
        "## Genome lineage",
        "",
        "| Genome | Gen | Best | Last | Trend | Accept rate | Plateaued |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for g in r["ranking"]:
        lines.append(
            f"| {g['genome']} | {g['generation']} | {g['best_score']} | {g['last_score']} "
            f"| {g['trend']:+} | {g['accept_rate']} | {'•' if g['plateaued'] else ''} |"
        )
    lines += ["", "## Top skills (EvoSkillOpt)", ""]
    for s in r["top_skills"]:
        lines.append(f"- **{s['skill']}** — value {s['value']} (pulls {s['pulls']})")
    lines += ["", f"Loadout: {', '.join(r['loadout']) or '—'}", ""]
    traj = r.get("trajectory")
    if traj:
        lines += [
            "## EvoMetaClaw moat",
            "",
            f"- Accumulated events: **{traj['total_events']}** across {traj['genomes']} genomes "
            f"({traj['total_bytes']} bytes)",
            "",
        ]
        for g, n in list(traj["by_genome"].items())[:10]:
            lines.append(f"- {g}: {n}")
        lines.append("")
    return "\n".join(lines)


def load_report(settings=None) -> Dict:
    """Load the population/skills from the trajectory store and build a report."""
    settings = settings or get_settings()
    store = TrajectoryStore()
    root = store.root
    forge = EvoForge(population_path=root / "_population.json")
    skillopt = EvoSkillOpt(skills_path=root / "_skills.json")
    return build_report(forge, skillopt, trajectory=store)


def main() -> None:
    report = load_report()
    if "--markdown" in sys.argv[1:] or "--md" in sys.argv[1:]:
        out = _to_markdown(report)
        # Optional file arg after the flag.
        paths = [a for a in sys.argv[1:] if not a.startswith("-")]
        if paths:
            Path(paths[0]).write_text(out, encoding="utf-8")
            print(f"wrote {paths[0]}")
        else:
            print(out)
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
