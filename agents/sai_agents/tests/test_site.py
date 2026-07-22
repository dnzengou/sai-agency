import json
import xml.etree.ElementTree as ET

from sai_agents.deals.site import (
    country_slug,
    deal_path,
    export_site,
    render_countries_index,
    render_country_page,
    render_deal_page,
    render_sitemap,
)

DEAL = {
    "id": "abc123", "title": "EIC Accelerator Open 2026", "org": "EISMEA",
    "country": "EU", "region": "EU", "city": "Brussels", "sector": "Deep tech / AI",
    "type": "grant", "value_eur": 414000000, "stage": "open", "deadline": "2026-09-09",
    "date": "2026-01-01", "source_url": "https://eic.example/call", "source_name": "EIC",
    "description": "A big EU grant for deep-tech SMEs.", "arm_stage": "qualified",
    "owner": "marketing", "next_action": "Check eligibility", "priority": "high",
    "impact_score": 0.82,
}


def test_render_deal_page_has_seo_and_form():
    html = render_deal_page(DEAL)
    assert "<title>EIC Accelerator Open 2026 · Deal Radar · SAI Agency</title>" in html
    assert '<link rel="canonical" href="https://sai-agency-deals-radar.netlify.app/deals/abc123"' in html
    assert 'property="og:title"' in html
    # JSON-LD present and valid
    start = html.index("application/ld+json\">") + len("application/ld+json\">")
    end = html.index("</script>", start)
    ld = json.loads(html[start:end])
    assert ld["@type"] == "WebPage" and ld["url"].endswith("/deals/abc123")
    # inline pre-filled Netlify form
    assert 'name="deal-interest"' in html
    assert 'value="EIC Accelerator Open 2026 · EISMEA"' in html
    assert 'href="https://eic.example/call"' in html


def test_render_deal_page_escapes_html():
    d = dict(DEAL, title='Bad <script>alert(1)</script> & "quote"')
    html = render_deal_page(d)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_sitemap_lists_all_deals():
    xml = render_sitemap([DEAL, dict(DEAL, id="def456")])
    root = ET.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in root.findall(".//s:loc", ns)]
    # The homepage serves the Deal Radar; /deals is its canonical URL, so the
    # sitemap lists /deals (not a bare / duplicate).
    assert "https://sai-agency-deals-radar.netlify.app/deals" in locs
    assert "https://sai-agency-deals-radar.netlify.app/" not in locs
    assert "https://sai-agency-deals-radar.netlify.app/deals/abc123" in locs
    assert "https://sai-agency-deals-radar.netlify.app/deals/def456" in locs


def test_export_site_writes_pages_and_prunes_stale(tmp_path):
    ds = {"deals": [DEAL, dict(DEAL, id="def456")]}
    res = export_site(ds, tmp_path)
    assert res["pages"] == 2
    assert (tmp_path / "deals" / "abc123.html").exists()
    assert (tmp_path / "sitemap.xml").exists()
    # regenerate with one fewer deal -> stale page pruned
    res2 = export_site({"deals": [DEAL]}, tmp_path)
    assert res2["removed"] == 1
    assert not (tmp_path / "deals" / "def456.html").exists()
    assert deal_path(DEAL) == "deals/abc123.html"


def test_country_slug():
    assert country_slug("Italy") == "italy"
    assert country_slug("United States") == "united-states"
    assert country_slug("US") == "us"
    assert country_slug("") == "other"


def test_render_country_page_seo():
    deals = [DEAL, dict(DEAL, id="d2", title="Second deal in EU")]
    html = render_country_page("EU", deals)
    assert "<title>Opportunities in EU · SAI Agency Deal Radar</title>" in html
    assert 'canonical" href="https://sai-agency-deals-radar.netlify.app/country/eu"' in html
    assert 'application/ld+json' in html
    assert "/deals/abc123" in html and "/deals/d2" in html
    assert 'href="/deals?country=EU"' in html


def test_render_countries_index_lists_and_orders():
    groups = {"Italy": [DEAL, DEAL, DEAL], "Spain": [DEAL]}
    html = render_countries_index(groups)
    assert "/country/italy" in html and "/country/spain" in html
    # Italy (3) should appear before Spain (1)
    assert html.index("/country/italy") < html.index("/country/spain")


def test_export_site_writes_country_pages(tmp_path):
    ds = {"deals": [
        dict(DEAL, id="a1", country="Italy"),
        dict(DEAL, id="a2", country="Italy"),
        dict(DEAL, id="a3", country="Spain"),
    ]}
    res = export_site(ds, tmp_path)
    assert res["country_pages"] == 2
    assert (tmp_path / "country" / "italy.html").exists()
    assert (tmp_path / "country" / "spain.html").exists()
    assert (tmp_path / "countries.html").exists()
    sm = (tmp_path / "sitemap.xml").read_text()
    assert "/country/italy" in sm and "/countries" in sm
    # stale country pages pruned on regenerate
    res2 = export_site({"deals": [dict(DEAL, id="a1", country="Italy")]}, tmp_path)
    assert not (tmp_path / "country" / "spain.html").exists()
