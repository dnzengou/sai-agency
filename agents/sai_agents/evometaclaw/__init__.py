"""EvoMetaClaw — the accumulated-trajectory moat.

OpenClaw can copy a skill registry. They cannot copy a SkillOpt-powered
self-evolving agent without rebuilding the entire training paradigm *and*
accumulating the trajectory data. This module is where that data accumulates.

Every :class:`EvolutionEvent` the KafCa publisher accepts is appended to an
append-only JSONL trajectory keyed by genome. The trajectories are the flywheel:
each run leaves durable ground-truth signal that population-based evolution
consumes.
"""

from sai_agents.evometaclaw.trajectory import TrajectoryStore

__all__ = ["TrajectoryStore"]
