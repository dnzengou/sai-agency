"""Tests for AI-agent-native SEO surfaces (llms.txt, agents.json, JSON-LD)."""

import json

from sai_agents.deals.agent_seo import (
    DEFAULT_SITE,
    deal_schema,
    dataset_schema,
    render_agents_manifest,
    render_llms_txt,
    render_robots_txt,
)
from sai_agents.deals.site import _json_ld, export_site


_DATASET = {
    "generated_at": "2026-11-07T12:00:00Z",
    "summary": {
        "total_deals": 2,
        "regions": ["EU", "Southern Europe"],
        "countries": ["Spain", "Italy"],
        "categories": ["ai_ml"],
        "evolved_order": True,
    },
    "deals": [
        {
            "id": "abc123",
            "title": "EIC Accelerator Open 2026",
            "org": "European Innovation Council",
            "country": "EU",
            "region": "EU",
            "sector": "AI/ML",
            "type": "grant",
            "category": "ai_ml",
            "value_eur": 2_500_000,
            "stage": "open",
            "deadline": "2026-09-01",
            "source_url": "https://eic.ec.europa.eu/",
            "description": "EIC Accelerator for deep-tech.",
            "impact_score": 0.82,
            "arm_priority": 0.88,
            "arm_rationale": ["Actionable now", "Large ticket"],
        },
        {
            "id": "def456",
            "title": "Italy €1 house (Sambuca)",
            "org": "Comune di Sambuca",
            "country": "Italy",
            "region": "Southern Europe",
            "sector": "Property",
            "type": "property_scheme",
            "category": "repopulation",
            "value_eur": None,
            "stage": "open",
            "deadline": None,
            "source_url": "https://example.test/",
            "description": "€1 property scheme in Sicily.",
            "impact_score": 0.6,
            "arm_priority": 0.7,
            "arm_rationale": ["Actionable now"],
        },
    ],
}


def test_deal_schema_grant_uses_funder_and_deadline():
    d = _DATASET["deals"][0]
    node = deal_schema(d, DEFAULT_SITE + "/deals/abc123")
    assert node["@type"] == "Grant"
    assert node["funder"]["name"] == "European Innovation Council"
    assert node["applicationDeadline"] == "2026-09-01"
    assert node["amount"] == {"@type": "MonetaryAmount", "currency": "EUR", "value": 2_500_000}
    assert node["url"] == "https://eic.ec.europa.eu/"
    # The EvoSkillOpt rationale and ARM priority surface as additionalProperty
    # so an agent can see WHY this deal ranks here, not just what it is.
    names = {p["name"] for p in node["additionalProperty"]}
    assert "arm_priority" in names and "rationale" in names


def test_deal_schema_property_scheme_uses_offeredby():
    d = _DATASET["deals"][1]
    node = deal_schema(d, DEFAULT_SITE + "/deals/def456")
    assert node["@type"] == "Offer"
    assert node["offeredBy"]["name"] == "Comune di Sambuca"
    assert node["areaServed"]["name"] == "Italy"
    # No value and no deadline on this one — those fields must be absent, not null.
    assert "amount" not in node and "applicationDeadline" not in node


def test_json_ld_embeds_graph_with_webpage_and_deal_node():
    raw = _json_ld(_DATASET["deals"][0], DEFAULT_SITE + "/deals/abc123")
    # Breakout chars are escaped.
    assert "<" not in raw and "</script>" not in raw
    # Un-escape just enough to parse back.
    recovered = raw.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    data = json.loads(recovered)
    types = {node.get("@type") for node in data["@graph"]}
    assert "WebPage" in types and "Grant" in types


def test_dataset_schema_lists_json_rss_sitemap():
    ds = dataset_schema(_DATASET["summary"])
    urls = {d["contentUrl"] for d in ds["distribution"]}
    assert any(u.endswith("/deals.json") for u in urls)
    assert any(u.endswith("/deals.xml") for u in urls)
    assert any(u.endswith("/sitemap.xml") for u in urls)
    assert ds["@type"] == "Dataset" and ds["name"].startswith("SAI Deal Radar")


def test_llms_txt_links_the_right_endpoints():
    txt = render_llms_txt(_DATASET)
    # Every machine-readable entry point an LLM should know about.
    for path in ("/deals.json", "/deals.xml", "/sitemap.xml", "/.well-known/agents.json", "/deals", "/countries"):
        assert path in txt, f"llms.txt missing {path}"
    # Top deals are listed with source-linked titles.
    assert "EIC Accelerator Open 2026" in txt
    assert txt.startswith("# SAI Deal Radar")


def test_agents_manifest_is_discoverable_and_well_shaped():
    m = render_agents_manifest(_DATASET)
    assert m["name"] == "SAI Deal Radar"
    assert set(m["endpoints"]) >= {"dataset", "feed_rss", "sitemap", "llms_txt", "home"}
    assert "pursue-a-deal" in m["capabilities"]
    assert m["data"]["total_deals"] == 2
    assert m["schema_version"] == 1


def test_robots_txt_names_major_ai_crawlers():
    txt = render_robots_txt()
    for ua in ("GPTBot", "OAI-SearchBot", "ClaudeBot", "Google-Extended",
               "PerplexityBot", "Applebot-Extended", "Amazonbot"):
        assert f"User-agent: {ua}" in txt, f"robots.txt missing {ua}"
    assert "Sitemap: https://sai-agency-deals-radar.netlify.app/sitemap.xml" in txt


def test_export_site_emits_llms_txt_agents_manifest_and_robots(tmp_path):
    res = export_site(_DATASET, tmp_path)
    # Emitted files all exist and are well-shaped.
    llms = (tmp_path / "llms.txt").read_text(encoding="utf-8")
    assert "# SAI Deal Radar" in llms
    manifest = json.loads((tmp_path / ".well-known" / "agents.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1 and manifest["endpoints"]["dataset"].endswith("/deals.json")
    robots = (tmp_path / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: GPTBot" in robots
    # The return receipt lists the new surfaces.
    assert res["llms_txt"].endswith("/llms.txt")
    assert res["agents_manifest"].endswith("/agents.json")


def test_sitemap_lists_agent_entry_points(tmp_path):
    export_site(_DATASET, tmp_path)
    xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert "/llms.txt" in xml
    assert "/.well-known/agents.json" in xml
