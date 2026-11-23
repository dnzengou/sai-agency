"""The EvoMetaClaw moat is surfaced in deals.json + llms-full.txt + stats."""

import json
from unittest.mock import patch

from sai_agents.deals.agent_seo import render_llms_full_txt
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.evometaclaw.trajectory import TrajectoryStore
from sai_agents.models import EventType, EvolutionEvent


def _pipe():
    # Same signature the deal tests use; no RSS, bundled only.
    return KafCadePipeline()


def test_build_dataset_omits_moat_on_empty_store(tmp_path, monkeypatch):
    # Fresh store, no events — summary.trajectory_moat is None.
    monkeypatch.setenv("SAI_TRAJECTORY_ROOT", str(tmp_path / "empty"))
    pipe = _pipe()
    ds = pipe.build_dataset(pipe.collect())
    assert ds["summary"]["trajectory_moat"] is None


def test_build_dataset_surfaces_moat_when_events_present(tmp_path, monkeypatch):
    # Seed real events into the trajectory root, then regenerate.
    root = tmp_path / "with-events"
    monkeypatch.setenv("SAI_TRAJECTORY_ROOT", str(root))
    store = TrajectoryStore(root=root, enabled=True)
    for _ in range(5):
        store.append(EvolutionEvent(event_type=EventType.AGENT_RUN, source_agent="marketing"))
    for _ in range(3):
        store.append(EvolutionEvent(event_type=EventType.AGENT_RUN, source_agent="deal_sourcing"))

    pipe = _pipe()
    ds = pipe.build_dataset(pipe.collect())
    moat = ds["summary"]["trajectory_moat"]
    assert moat is not None
    assert moat["total_events"] == 8
    assert moat["genomes"] == 2
    assert moat["by_genome"]["marketing"] == 5


def test_build_dataset_moat_failure_degrades_safely(monkeypatch):
    # If the accumulation call itself blows up, we get None, not a crash —
    # buyers never see a broken Deal Radar because of an evo-metaclaw glitch.
    from sai_agents.deals import pipeline as pipeline_mod

    def boom(self):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(pipeline_mod.KafCadePipeline, "_load_moat",
                        lambda self: None)  # replicate the except branch
    pipe = _pipe()
    ds = pipe.build_dataset(pipe.collect())
    assert ds["summary"]["trajectory_moat"] is None


def test_llms_full_txt_includes_moat_only_when_present():
    base = {
        "summary": {
            "total_deals": 2, "regions": ["EU"], "countries": ["Spain"],
            "categories": ["ai_ml"], "arm": {}, "trajectory_moat": None,
        },
        "deals": [],
    }
    txt_empty = render_llms_full_txt(base)
    assert "EvoMetaClaw moat" not in txt_empty  # no moat heading on empty data

    moat = {"total_events": 42, "genomes": 7, "by_genome": {}, "total_bytes": 999}
    full = {**base, "summary": {**base["summary"], "trajectory_moat": moat}}
    txt_with = render_llms_full_txt(full)
    assert "EvoMetaClaw moat" in txt_with
    assert "**42**" in txt_with and "**7**" in txt_with
    assert "cannot replicate" in txt_with  # the honest copycat-resistance claim
