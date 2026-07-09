from sai_agents.config import Settings
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.deals.rss import (
    RSSSource,
    classify_sector,
    classify_type,
    infer_country_region,
    parse_feed,
)
from sai_agents.models import DealType

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>EU Startups</title>
  <item>
    <title>Stockholm-based AI startup raises €20 million Series A</title>
    <description>A Swedish AI company raised a Series A led by a VC.</description>
    <link>https://example.com/a</link>
    <pubDate>Mon, 02 Feb 2026 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Italy opens public tender for AI data platform</title>
    <description>A procurement notice for AI services in healthcare.</description>
    <link>https://example.com/b</link>
    <pubDate>Tue, 03 Mar 2026 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Global accelerator cohort announced</title>
    <description>An accelerator programme with no geography named.</description>
    <link>https://example.com/c</link>
  </item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Tech</title>
  <entry>
    <title>Finnish cloud firm secures €100 million for GPU infrastructure</title>
    <summary>Helsinki GPU cloud provider funding round.</summary>
    <link href="https://example.com/d"/>
    <updated>2026-04-24T00:00:00Z</updated>
  </entry>
</feed>"""


def test_classify_type():
    assert classify_type("Startup raises €20M Series A") == "funding_round"
    assert classify_type("Government opens public tender for AI") == "public_tender"
    assert classify_type("New AI accelerator cohort") == "accelerator"
    assert classify_type("Ministry launches funding call / grant") == "grant"
    assert classify_type("Two firms announce a strategic partnership") == "partnership"
    assert classify_type("Some neutral headline") == "partnership"  # default


def test_classify_sector_and_region():
    assert classify_sector("clinical patient AI") == "HealthTech"
    assert classify_sector("gpu cloud compute") == "Data infrastructure"
    country, region = infer_country_region("A Swedish company in Stockholm")
    assert country == "Sweden" and region == "Nordics"
    country, region = infer_country_region("An Italian firm")
    assert country == "Italy" and region == "Southern Europe"
    assert infer_country_region("no country here")[1] == "EU"


def test_parse_rss_feed():
    deals = parse_feed(RSS_XML, "eu-startups")
    assert len(deals) == 3
    a = deals[0]
    assert a["type"] == "funding_round"
    assert a["country"] == "Sweden" and a["region"] == "Nordics"
    assert a["source_url"] == "https://example.com/a"
    assert a["confidence"] == 0.4
    assert deals[1]["type"] == "public_tender"


def test_parse_atom_feed():
    deals = parse_feed(ATOM_XML, "tech")
    assert len(deals) == 1
    assert deals[0]["type"] == "funding_round"
    assert deals[0]["region"] == "Nordics"
    assert deals[0]["source_url"] == "https://example.com/d"


def test_rss_source_with_injected_fetcher_and_region_filter():
    src = RSSSource(
        "https://feed.example/rss",
        fetcher=lambda url, timeout: RSS_XML,
        region_filter={"Southern Europe", "Nordics"},
    )
    got = src.fetch()
    # The "Global accelerator" item (region EU) is filtered out.
    assert len(got) == 2
    assert {d["region"] for d in got} == {"Nordics", "Southern Europe"}


def test_rss_source_network_error_is_contained():
    def boom(url, timeout):
        raise OSError("dns fail")

    assert RSSSource("https://x", fetcher=boom).fetch() == []


def test_pipeline_merges_rss_with_bundled(monkeypatch):
    # Feed the pipeline an RSS source via settings + a stubbed fetcher.
    settings = Settings(kafka_enabled=False, rss_feeds=["https://feed.example/rss"])
    pipe = KafCadePipeline(settings=settings)
    # Replace the network fetch on every RSSSource instance in the registry.
    for src in pipe.registry._sources:
        if isinstance(src, RSSSource):
            src._fetch = lambda url, timeout: RSS_XML
    deals = pipe.collect()
    # bundled (32) + 2 region-matching RSS items (accelerator dropped by filter).
    assert len(deals) >= 34
    assert any(d.source_name.startswith("rss:") for d in deals)
