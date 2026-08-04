"""EvoSkillOpt — skill-level credit assignment over accumulated trajectories.

Where EvoForge evolves *behavioural knobs*, EvoSkillOpt answers a sharper
question: *which skills actually pay off?* Every ``Insight`` an agent emits
carries ``tags`` (its skills) and an ``impact_score`` (its reward). EvoSkillOpt
treats each tag as an arm of a multi-armed bandit and runs UCB1 credit
assignment across the whole trajectory, accumulating a persistent, EMA-smoothed
value per skill.

The output is a ranked skill table plus a recommended top-N *loadout* — the
skills worth exercising next — emitted back onto the KafCa stream as an
``EVOLUTION_SIGNAL`` so the flywheel keeps turning.
"""

from sai_agents.evoskillopt.optimizer import (
    EvoSkillOpt,
    SkillReport,
    SkillStat,
    skills_from_events,
)

__all__ = ["EvoSkillOpt", "SkillReport", "SkillStat", "skills_from_events"]
