"""agent_seo — AI-agent-native SEO surfaces for the Deal Radar.

Classic SEO served human search; agents (ChatGPT, Claude, Perplexity, Gemini,
SearchGPT, and the coming wave of buying agents) need different surfaces. This
module emits them alongside the normal HTML pages:

  * ``/llms.txt`` — the emerging markdown curation standard (Jeremy Howard
    proposal) giving LLMs a map of what the site offers and where to read it.
  * ``/.well-known/agents.json`` — a programmatic entry point agents can
    discover under ``.well-known`` listing the dataset endpoints, feeds and
    pursue-a-deal flow.
  * Per-deal schema.org structured data — richer than a plain WebPage: a
    ``Grant`` for grants, an ``Offer`` for business-succession and property
    schemes, an ``InvestmentFund``/``Dataset`` where that fits the type, with
    ``url``, ``funder``, ``applicationDeadline``, ``areaServed`` and the deal's
    EvoSkillOpt tags surfaced as ``additionalProperty`` — so an agent can
    parse the opportunity, not just read the prose.
  * A collection-level ``Dataset`` for the whole Deal Radar on the index page,
    so an agent can discover the JSON endpoint and subscribe via RSS.

All surfaces are generated deterministically from ``deals.json`` so they match
what humans see; nothing is fabricated for agents alone.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

DEFAULT_SITE = "https://sai-agency-deals-radar.netlify.app"

# schema.org type per DealType — picked to match what an agent would expect to
# parse. Everything else falls back to Offer.
_SCHEMA_TYPE = {
    "grant": "Grant",
    "public_tender": "Grant",
    "accelerator": "Offer",
    "funding_round": "InvestmentOrDeposit",
    "partnership": "Offer",
    "rfp": "Grant",
    "property_scheme": "Offer",
    "business_succession": "Offer",
    "venture": "InvestmentOrDeposit",
}


def deal_schema(deal: Dict, url: str) -> Dict:
    """Richer schema.org representation of a single deal.

    The returned dict is a JSON-LD node with a type picked to match the deal's
    nature, so an agent can reason about it (a grant has an
    ``applicationDeadline``, an investment vehicle has an ``issuedBy``, an
    offer has an ``areaServed``). Returned as a plain dict so the caller can
    embed it in a larger JSON-LD graph.
    """
    dtype = str(deal.get("type", "")).lower()
    schema_type = _SCHEMA_TYPE.get(dtype, "Offer")
    node: Dict = {
        "@type": schema_type,
        "name": deal.get("title", ""),
        "description": deal.get("description", ""),
        "url": deal.get("source_url") or url,
        "identifier": deal.get("id"),
    }

    # Area served / country.
    country = (deal.get("country") or "").strip()
    region = (deal.get("region") or "").strip()
    if country or region:
        node["areaServed"] = {
            "@type": "Place",
            "name": country or region,
            "containedInPlace": ({"@type": "Place", "name": region} if region and region != country else None),
        }
        if node["areaServed"]["containedInPlace"] is None:
            node["areaServed"].pop("containedInPlace")

    # Funder / issuer — same org field, mapped to the right property per type.
    org = (deal.get("org") or "").strip()
    if org:
        org_node = {"@type": "Organization", "name": org}
        if schema_type == "Grant":
            node["funder"] = org_node
        elif schema_type == "InvestmentOrDeposit":
            node["issuedBy"] = org_node
        else:
            node["offeredBy"] = org_node

    # Monetary value, if known.
    if deal.get("value_eur"):
        node["amount"] = {
            "@type": "MonetaryAmount",
            "currency": "EUR",
            "value": deal["value_eur"],
        }

    # Deadline — typed field agents can act on.
    if deal.get("deadline"):
        key = "applicationDeadline" if schema_type == "Grant" else "validThrough"
        node[key] = deal["deadline"]

    # EvoSkillOpt tags and ARM rationale: surface as additionalProperty so an
    # agent can see WHY this deal ranks here, not just what it is.
    props: List[Dict] = []
    if deal.get("sector"):
        props.append({"@type": "PropertyValue", "name": "sector", "value": deal["sector"]})
    if deal.get("arm_priority") is not None:
        props.append({"@type": "PropertyValue", "name": "arm_priority", "value": deal["arm_priority"]})
    for reason in deal.get("arm_rationale") or []:
        props.append({"@type": "PropertyValue", "name": "rationale", "value": reason})
    if props:
        node["additionalProperty"] = props

    # Clean Nones so the JSON stays tight.
    return {k: v for k, v in node.items() if v not in (None, "", [], {})}


def dataset_schema(summary: Dict, site_url: str = DEFAULT_SITE) -> Dict:
    """Collection-level schema.org ``Dataset`` so an agent discovers the feed."""
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "SAI Deal Radar — AI/ML grants, business succession, property schemes, venture vehicles",
        "description": (
            "A continuously-refreshed, cited list of real AI/ML, business "
            "succession, property-relocation and venture opportunities sourced "
            "worldwide, ARM-classified and impact-ranked."
        ),
        "url": f"{site_url}/deals",
        "keywords": [
            "AI grants", "business succession", "venture funds", "property schemes",
            "relocation grants", "public tenders", "accelerators",
        ],
        "creator": {"@type": "Organization", "name": "SAI Agency"},
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{site_url}/deals.json"},
            {"@type": "DataDownload", "encodingFormat": "application/rss+xml", "contentUrl": f"{site_url}/deals.xml"},
            {"@type": "DataDownload", "encodingFormat": "application/xml", "contentUrl": f"{site_url}/sitemap.xml"},
        ],
        "temporalCoverage": summary.get("generated_at") or datetime.now(timezone.utc).date().isoformat(),
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "total_deals", "value": summary.get("total_deals")},
            {"@type": "PropertyValue", "name": "countries", "value": len(summary.get("countries", []))},
            {"@type": "PropertyValue", "name": "regions", "value": len(summary.get("regions", []))},
        ],
    }


# --------------------------------------------------------------------------- #
# llms.txt — markdown curation for LLMs.
# --------------------------------------------------------------------------- #
def render_llms_txt(dataset: Dict, site_url: str = DEFAULT_SITE) -> str:
    """Render the ``/llms.txt`` file — a curated map of the site for LLMs.

    Follows the emerging proposal: a markdown file whose structure gives an LLM
    a short, authoritative description plus an indexable list of the key URLs
    it should follow (and skip).
    """
    summary = dataset.get("summary", {})
    total = summary.get("total_deals", len(dataset.get("deals", [])))
    countries = len(summary.get("countries") or [])
    regions = len(summary.get("regions") or [])
    top = (dataset.get("deals") or [])[:10]

    lines = [
        "# SAI Deal Radar",
        "",
        (
            "> Continuously-refreshed radar of real, source-cited opportunities: "
            "AI/ML grants, business-succession listings, property/relocation "
            f"schemes and venture vehicles — {total} deals across {countries} "
            f"countries in {regions} regions. Every entry links to its official "
            "source. ARM-classified and impact-ranked (see JSON for the full "
            "`arm_priority` and `arm_rationale` per deal)."
        ),
        "",
        "## Primary data (machine-readable)",
        "",
        f"- [Full dataset (JSON)]({site_url}/deals.json): every deal with impact "
        "score, ARM stage, next action, evolved arm_priority and rationale.",
        f"- [Deal feed (RSS 2.0)]({site_url}/deals.xml): subscribe to new deals.",
        f"- [Sitemap]({site_url}/sitemap.xml): every deal page.",
        f"- [Agent manifest]({site_url}/.well-known/agents.json): programmatic "
        "entry point for agent discovery.",
        "",
        "## Human pages",
        "",
        f"- [Deal Radar (home)]({site_url}/deals): filterable radar.",
        f"- [By country]({site_url}/countries): per-country landing pages.",
        f"- [Demo pathways]({site_url}/demo): succession / repopulation / venture.",
        f"- [Match]({site_url}/match): matchmaker from a pasted business plan.",
        "",
        "## Top deals right now",
        "",
    ]
    for d in top:
        lines.append(
            f"- [{d.get('title','')}]({site_url}/deals/{d.get('id')}): "
            f"{d.get('country','')} · {d.get('type','')} · impact "
            f"{d.get('impact_score', 0):.2f}"
            + (f" · deadline {d['deadline']}" if d.get("deadline") else "")
        )
    lines += [
        "",
        "## Optional",
        "",
        f"- [Per-country pages]({site_url}/countries) — each country page is a "
        "focused landing surface; use these for geographic queries.",
        f"- [Full deal detail pages]({site_url}/deals/<id>) — one page per "
        "deal, with JSON-LD and a direct \"pursue\" form.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# /.well-known/agents.json — programmatic agent discovery.
# --------------------------------------------------------------------------- #
def render_agents_manifest(dataset: Dict, site_url: str = DEFAULT_SITE) -> Dict:
    """A small JSON manifest at /.well-known/agents.json that lets an agent
    discover what this site offers and where to read it.

    The shape is deliberately minimal and self-describing — not tied to one
    vendor's spec — so any agent crawler can consume it: name, description,
    endpoints, and a short list of capabilities.
    """
    summary = dataset.get("summary", {})
    return {
        "name": "SAI Deal Radar",
        "description": (
            "Agent-readable radar of real, source-cited AI/ML, business "
            "succession, property and venture opportunities worldwide."
        ),
        "contact": f"{site_url}/match",
        "endpoints": {
            "dataset": f"{site_url}/deals.json",
            "feed_rss": f"{site_url}/deals.xml",
            "sitemap": f"{site_url}/sitemap.xml",
            "llms_txt": f"{site_url}/llms.txt",
            "home": f"{site_url}/deals",
        },
        "capabilities": [
            "browse-opportunities",
            "filter-by-country-region-type-category",
            "subscribe-weekly-digest",
            "pursue-a-deal",
            "match-from-business-plan",
        ],
        "data": {
            "total_deals": summary.get("total_deals"),
            "regions": summary.get("regions"),
            "categories": summary.get("categories"),
            "evolved_order": summary.get("evolved_order", False),
        },
        "schema_version": 1,
        "generated_at": dataset.get("generated_at"),
    }


def render_robots_txt(site_url: str = DEFAULT_SITE) -> str:
    """Modern robots.txt that is explicit about the AI-crawler landscape.

    Classic SEO allowed everything by default; modern SEO benefits from being
    explicit about the major AI crawlers, so each one sees a signal rather
    than inferring it. We allow them all — that's the goal, to be
    agent-discoverable — but naming them makes robots-driven monitoring and
    polite revocation possible later.
    """
    ai_agents = [
        "GPTBot",  # OpenAI training crawler
        "OAI-SearchBot",  # OpenAI SearchGPT index
        "ChatGPT-User",  # OpenAI user-fetching crawler
        "ClaudeBot",  # Anthropic training crawler
        "Claude-Web",  # Anthropic user-fetching crawler
        "anthropic-ai",  # Anthropic (legacy alias)
        "Google-Extended",  # Google Bard/Vertex AI
        "PerplexityBot",  # Perplexity training
        "Perplexity-User",  # Perplexity user-fetching
        "Applebot-Extended",  # Apple AI training
        "Meta-ExternalAgent",  # Meta AI user-fetching
        "Meta-ExternalFetcher",  # Meta AI fetcher
        "Amazonbot",  # Amazon Alexa / AI
        "Bytespider",  # ByteDance (TikTok) AI crawler
        "DuckAssistBot",  # DuckDuckGo DuckAssist
        "YouBot",  # You.com
        "cohere-ai",  # Cohere
        "Diffbot",  # Diffbot knowledge graph
    ]
    sections = [
        "# SAI Deal Radar — robots.txt",
        "# Agent-discoverable by design: every deal links to its official",
        "# source, so AI crawlers add signal, not scrape risk.",
        "",
        "User-agent: *",
        "Allow: /",
        "",
    ]
    for ua in ai_agents:
        sections.append(f"User-agent: {ua}")
        sections.append("Allow: /")
        sections.append("")
    sections += [
        f"Sitemap: {site_url}/sitemap.xml",
        f"# Agent-first entry points:",
        f"# - {site_url}/llms.txt",
        f"# - {site_url}/.well-known/agents.json",
        f"# - {site_url}/deals.json",
        "",
    ]
    return "\n".join(sections)
