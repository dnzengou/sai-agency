"""Pytest fixtures — keep tests hermetic.

The KafCa publisher now owns an EvoMetaClaw ``TrajectoryStore`` that writes
every accepted event to ``~/.sai/trajectories/`` by default. That is exactly
the behaviour we want in production (the flywheel is ON by default), but in
tests we route it into a per-session tmp path so we never pollute the user's
home directory.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_trajectory_root():
    with tempfile.TemporaryDirectory(prefix="sai-trajectories-") as tmp:
        prev = os.environ.get("SAI_TRAJECTORY_ROOT")
        os.environ["SAI_TRAJECTORY_ROOT"] = tmp
        try:
            yield
        finally:
            if prev is None:
                os.environ.pop("SAI_TRAJECTORY_ROOT", None)
            else:
                os.environ["SAI_TRAJECTORY_ROOT"] = prev
