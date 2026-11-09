"""Tests for the GEO (llms-full.txt), ai.txt / security.txt, and agents_check."""

import json
from unittest.mock import patch

from sai_agents.deals.agent_seo import (
    render_ai_txt,
    render_llms_full_txt,
    render_security_txt,
)
from sai_agents.deals import agents_check
from sai_agents.deals.site import export_site


_DATASET = {
    "generated_at": "2026-11-08T12:00:00Z",
    "schema_version": 1,
    "summary": {
        "total_deals": 2, "regions": ["EU"], "countries": ["Spain"],
        "categories": ["ai_ml"],
        "arm": {
            "by_arm_stage": {"qualified": 1, "lost": 1},
            "portfolio": {
                "business":  {"count": 0, "open": 0, "avg_impact": 0.0, "value_eur": 0},
                "property":  {"count": 0, "open": 0, "avg_impact": 0.0, "value_eur": 0},
                "ai_deals":  {"count": 2, "open": 1, "avg_impact": 0.7, "value_eur": 1_000_000},
                "ventures":  {"count": 0, "open": 0, "avg_impact": 0.0, "value_eur": 0},
            },
        },
    },
    "deals": [
        {"id": "x", "title": "T", "stage": "open", "type": "grant", "source_url": "https://ex.test"},
    ],
}


def test_llms_full_txt_is_grounded_and_cites_code():
    txt = render_llms_full_txt(_DATASET)
    # Every FAQ answer must reference a real file in the repo.
    for anchor in (
        "agents/sai_agents/deals/pipeline.py",
        "agents/sai_agents/kafca/impact.py",
        "agents/sai_agents/deals/arm.py",
        "agents/sai_agents/evoforge/",
        "agents/sai_agents/evoskillopt/",
        "agents/sai_agents/evometaclaw/",
        "TRANSPARENCY.md",
        "CITATION.cff",
        ".github/workflows/deal-refresh.yml",
        ".github/workflows/evo-cycle.yml",
    ):
        assert anchor in txt, f"llms-full.txt missing anchor {anchor}"
    # The portfolio + stage snapshots render.
    assert "ai_deals: 2 deals" in txt
    assert "qualified: 1" in txt
    # The anti-cloaking disclosures are present verbatim.
    assert "No cloaking" in txt and "No fabricated" in txt


def test_ai_txt_declares_policy_explicitly():
    txt = render_ai_txt()
    assert "License: CC-BY-4.0" in txt
    assert "Training: allowed" in txt
    assert "Inference: allowed" in txt
    assert "Citation: required" in txt
    assert "TRANSPARENCY.md" in txt


def test_security_txt_has_rfc9116_fields():
    txt = render_security_txt()
    for field in ("Contact:", "Expires:", "Preferred-Languages:", "Policy:", "Canonical:"):
        assert field in txt, f"security.txt missing {field}"
    # Expiry is a parseable ISO-8601 UTC timestamp.
    expires = [line for line in txt.splitlines() if line.startswith("Expires:")][0].split(" ", 1)[1]
    from datetime import datetime
    assert datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ")


def test_export_site_emits_llms_full_ai_and_security(tmp_path):
    res = export_site(_DATASET, tmp_path)
    assert (tmp_path / "llms-full.txt").read_text().startswith("# SAI Deal Radar — grounded facts")
    assert "Training: allowed" in (tmp_path / ".well-known" / "ai.txt").read_text()
    assert "Contact:" in (tmp_path / ".well-known" / "security.txt").read_text()
    for key in ("llms_full_txt", "ai_txt", "security_txt"):
        assert key in res


def test_sitemap_lists_llms_full_txt(tmp_path):
    export_site(_DATASET, tmp_path)
    xml = (tmp_path / "sitemap.xml").read_text()
    assert "/llms-full.txt" in xml


# ---------- agents_check CLI ---------- #
def _fake_fetch_factory(responses):
    """Return a fake _fetch(url) that serves the given {path: (status, body)}."""
    def _fetch(url):
        for path, resp in responses.items():
            if url.endswith(path):
                return resp
        raise AssertionError(f"unexpected fetch: {url}")
    return _fetch


def test_agents_check_passes_on_good_deployment():
    manifest = {
        "endpoints": {"dataset": "x", "feed_rss": "y", "sitemap": "z", "home": "/"},
        "capabilities": ["browse-opportunities"],
    }
    fake = _fake_fetch_factory({
        "/deals.json": (200, json.dumps({"schema_version": 1, "deals": [{"id": "a"}]})),
        "/llms.txt": (200, "# SAI Deal Radar\n\n..."),
        "/.well-known/agents.json": (200, json.dumps(manifest)),
        "/robots.txt": (200, "\n".join(f"User-agent: {ua}\nAllow: /" for ua in (
            "GPTBot", "OAI-SearchBot", "ClaudeBot", "Google-Extended", "PerplexityBot"))),
        "/sitemap.xml": (200, "<urlset><url><loc>/llms.txt</loc></url><url><loc>/.well-known/agents.json</loc></url></urlset>"),
    })
    with patch.object(agents_check, "_fetch", fake):
        ok, fail = agents_check.check("https://example.test")
    assert fail == [], f"unexpected failures: {fail}"
    assert len(ok) == 5


def test_agents_check_flags_missing_crawlers_and_wrong_schema():
    fake = _fake_fetch_factory({
        "/deals.json": (200, json.dumps({"schema_version": 2, "deals": [{"id": "a"}]})),
        "/llms.txt": (200, "# ok\n"),
        "/.well-known/agents.json": (200, json.dumps({"endpoints": {"home": "/"}})),
        "/robots.txt": (200, "User-agent: *\nAllow: /"),
        "/sitemap.xml": (200, "<urlset></urlset>"),
    })
    with patch.object(agents_check, "_fetch", fake):
        ok, fail = agents_check.check("https://example.test")
    joined = " | ".join(fail)
    assert "schema_version=2" in joined
    assert "missing endpoints" in joined
    assert "missing crawlers" in joined
    assert "/sitemap.xml" in joined
