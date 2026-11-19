"""Tests for the ntfy push-digest publisher."""

import json
from unittest.mock import MagicMock

from sai_agents.digest.ntfy import (
    NtfyConfig,
    NtfyPublisher,
    SLICES,
    _topic_name,
    group_deals_by_topic,
    topic_catalog,
)


def _dataset():
    return {
        "generated_at": "2026-11-19T12:00:00Z",
        "deals": [
            {"id": "a1", "title": "EIC Accelerator 2026", "stage": "open",
             "category": "ai_ml", "region": "EU", "country": "EU", "type": "grant",
             "impact_score": 0.88, "arm_priority": 0.88, "deadline": "2026-09-01",
             "source_url": "https://eic.example"},
            {"id": "b2", "title": "Blocket verksamhet", "stage": "open",
             "category": "succession", "region": "Nordics", "country": "Sweden",
             "type": "business_succession", "impact_score": 0.6, "arm_priority": 0.6,
             "source_url": "https://blocket.se"},
            {"id": "c3", "title": "€1 Sambuca", "stage": "open",
             "category": "repopulation", "region": "Southern Europe", "country": "Italy",
             "type": "property_scheme", "impact_score": 0.55, "arm_priority": 0.55},
            # Announced is backlog — must NOT be pushed.
            {"id": "d4", "title": "Closed round", "stage": "announced",
             "category": "ai_ml", "region": "EU", "type": "funding_round",
             "impact_score": 0.9, "arm_priority": 0.9},
            # Low-impact — must stay out of the high-impact slice.
            {"id": "e5", "title": "Small grant", "stage": "open",
             "category": "ai_ml", "region": "Nordics", "country": "Sweden",
             "type": "grant", "impact_score": 0.3, "arm_priority": 0.3},
        ],
    }


def test_slices_are_unique_and_legible():
    slugs = [s[0] for s in SLICES]
    assert len(slugs) == len(set(slugs)), "duplicate slug in SLICES"
    # Must include at least these buckets so the UI panel stays useful.
    for required in ("all", "high-impact", "ai-ml", "succession", "property", "venture", "nordics"):
        assert required in slugs


def test_group_excludes_backlog_stages_and_respects_high_impact_cutoff():
    cfg = NtfyConfig()
    groups = group_deals_by_topic(_dataset(), cfg)
    all_ids = [d["id"] for d in groups["all"]]
    # Announced deal "d4" is excluded.
    assert "d4" not in all_ids
    # The high-impact slice contains only >= 0.75 impact deals.
    hi = groups.get("high-impact") or []
    assert all(d["impact_score"] >= 0.75 for d in hi)
    assert [d["id"] for d in hi] == ["a1"]


def test_group_respects_max_per_topic():
    cfg = NtfyConfig(max_per_topic=1)
    groups = group_deals_by_topic(_dataset(), cfg)
    # 4 open deals, capped to 1 in the "all" slice.
    assert len(groups["all"]) == 1


def test_topic_name_is_deterministic_and_prefixed():
    cfg = NtfyConfig(topic_prefix="my-deals-v2")
    assert _topic_name(cfg, "nordics") == "my-deals-v2-nordics"


def test_publish_dry_run_writes_preview_and_sends_nothing(tmp_path):
    cfg = NtfyConfig(server="https://ntfy.sh")
    posts = []
    pub = NtfyPublisher(
        config=cfg,
        post_fn=lambda url, body, hdrs: posts.append((url, body, hdrs)) or (200, "ok"),
        preview_path=str(tmp_path / "preview.json"),
    )
    res = pub.publish(_dataset(), dry_run=True)
    assert res["sent"] == 0
    assert res["dry_run"] == res["topics"] >= 1
    assert posts == []  # transport never called
    preview = json.loads((tmp_path / "preview.json").read_text())
    assert all("topic" in p and "title" in p and "click" in p for p in preview)


def test_publish_posts_one_message_per_non_empty_topic(monkeypatch):
    # Explicitly enable by setting the env var before constructing cfg.
    monkeypatch.setenv("SAI_NTFY_SERVER", "https://ntfy.test")
    cfg = NtfyConfig.from_env()
    assert cfg.enabled

    posts = []
    def fake_post(url, body, headers):
        posts.append({"url": url, "body": body.decode(), "headers": headers})
        return 200, "ok"

    pub = NtfyPublisher(config=cfg, post_fn=fake_post)
    res = pub.publish(_dataset(), dry_run=False)
    assert res["failed"] == 0
    assert res["sent"] == res["topics"] >= 1
    # Every POST goes to <server>/<topic>, with Title + Priority + Click headers.
    for p in posts:
        assert p["url"].startswith("https://ntfy.test/sai-deals-v1-")
        for h in ("Title", "Priority", "Tags", "Click", "Content-Type"):
            assert h in p["headers"]
        assert p["headers"]["Click"].startswith("https://")
    # The high-impact post has priority 4 (bumped).
    hi = next(p for p in posts if p["url"].endswith("-high-impact"))
    assert hi["headers"]["Priority"] == "4"
    # Default slices get priority 3.
    other = next(p for p in posts if p["url"].endswith("-all"))
    assert other["headers"]["Priority"] == "3"


def test_publish_http_errors_are_counted_per_topic(monkeypatch):
    monkeypatch.setenv("SAI_NTFY_SERVER", "https://ntfy.test")
    cfg = NtfyConfig.from_env()

    seen = []
    def flaky_post(url, body, headers):
        seen.append(url)
        # Return 500 for the first POST, 200 for the rest.
        return (500 if len(seen) == 1 else 200), "x"

    pub = NtfyPublisher(config=cfg, post_fn=flaky_post)
    res = pub.publish(_dataset(), dry_run=False)
    assert res["failed"] == 1
    assert res["sent"] == res["topics"] - 1


def test_publish_adds_bearer_when_token_configured(monkeypatch):
    monkeypatch.setenv("SAI_NTFY_SERVER", "https://ntfy.test")
    cfg = NtfyConfig.from_env()
    cfg.token = "tok_123"

    captured = []
    pub = NtfyPublisher(
        config=cfg,
        post_fn=lambda u, b, h: (captured.append(h) or (200, "ok")),
    )
    pub.publish(_dataset(), dry_run=False)
    assert all(h.get("Authorization") == "Bearer tok_123" for h in captured)


def test_topic_catalog_matches_slices_and_builds_subscribe_urls():
    cfg = NtfyConfig(server="https://ntfy.sh", topic_prefix="sai-deals-v1")
    cat = topic_catalog(cfg)
    assert len(cat) == len(SLICES)
    ai_ml = next(e for e in cat if e["slug"] == "ai-ml")
    assert ai_ml["topic"] == "sai-deals-v1-ai-ml"
    assert ai_ml["subscribe_url"] == "https://ntfy.sh/sai-deals-v1-ai-ml"
    assert ai_ml["deep_link"] == "ntfy://subscribe/sai-deals-v1-ai-ml"
