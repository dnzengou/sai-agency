"""Static site generation for the Deal Radar — SEO-first.

Emits one self-contained HTML page per deal (``/deals/<id>.html``) with unique
title/description, canonical + OpenGraph/Twitter tags, JSON-LD structured data,
and an inline (no-JS) pre-filled ``deal-interest`` Netlify form. Also renders a
full ``sitemap.xml`` covering the home page, the Deal Radar, and every deal —
so each opportunity is an indexable, shareable surface.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Dict, List

DEFAULT_SITE = "https://sai-agency-deals-radar.netlify.app"

_TYPE_LABEL = {
    "grant": "Grant",
    "public_tender": "Public tender",
    "accelerator": "Accelerator",
    "funding_round": "Funding round",
    "partnership": "Partnership",
    "rfp": "RFP",
    "property_scheme": "Relocation / €1 house",
    "business_succession": "Business succession",
    "venture": "Venture / co-investment",
}
_CAT_LABEL = {
    "ai_ml": "AI / ML",
    "repopulation": "Repopulation",
    "succession": "Succession",
    "venture": "Venture",
}


def country_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "other"


def _esc(v: object) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def euro(n) -> str:
    if not n:
        return "—"
    n = float(n)
    if n >= 1e9:
        return f"€{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"€{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"€{round(n / 1e3)}k"
    return f"€{n:.0f}"


def _valuation_str(v) -> str:
    """Human string for a valuation dict, including its short note."""
    if not v:
        return ""
    from sai_agents.valuation.estimator import format_estimate

    s = format_estimate(v)
    note = v.get("note") or ""
    return f"{s} — {note}" if note else s


def deal_path(deal: Dict) -> str:
    return f"deals/{deal['id']}.html"


def deal_url(deal: Dict, site_url: str = DEFAULT_SITE) -> str:
    return f"{site_url}/deals/{deal['id']}"


def _json_ld(deal: Dict, url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": deal.get("title", ""),
        "description": deal.get("description", ""),
        "url": url,
        "dateModified": deal.get("date") or None,
        "about": {
            "@type": "Organization",
            "name": deal.get("org") or deal.get("title", ""),
        },
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Deal Radar", "item": f"{DEFAULT_SITE}/deals"},
                {"@type": "ListItem", "position": 2, "name": deal.get("title", "")},
            ],
        },
    }
    data = {k: v for k, v in data.items() if v is not None}
    # JSON-LD in a non-executable script type is not subject to CSP script-src,
    # but we must still neutralise `<`/`>`/`&` so a value containing
    # "</script>" cannot break out of the script element.
    raw = json.dumps(data, ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_deal_page(deal: Dict, site_url: str = DEFAULT_SITE) -> str:
    url = deal_url(deal, site_url)
    title = deal.get("title", "Deal")
    desc = (deal.get("description") or title)[:300]
    tlabel = _TYPE_LABEL.get(deal.get("type", ""), deal.get("type", ""))
    org_line = " · ".join(filter(None, [deal.get("org"), deal.get("city"), deal.get("country")]))

    def meta_row(label: str, value: str) -> str:
        if not value or value == "—":
            return ""
        return f'<div class="drow"><span class="dk">{_esc(label)}</span><span class="dv">{_esc(value)}</span></div>'

    _CAT_LABEL = {"ai_ml": "AI / ML", "repopulation": "Repopulation", "succession": "Succession", "venture": "Venture"}
    rows = "".join([
        meta_row("Type", tlabel),
        meta_row("Category", _CAT_LABEL.get(deal.get("category", ""), deal.get("category", ""))),
        meta_row("Region", deal.get("region", "")),
        meta_row("Country", deal.get("country", "")),
        meta_row("Sector", deal.get("sector", "")),
        meta_row("Deal value", euro(deal.get("value_eur"))),
        meta_row("Indicative valuation", _valuation_str(deal.get("valuation"))),
        meta_row("Stage", deal.get("stage", "")),
        meta_row("Deadline", deal.get("deadline") or ""),
        meta_row("Pipeline stage (ARM)", f"{deal.get('arm_stage', '')} · owner {deal.get('owner', '')}"),
        meta_row("Impact score", f"{deal.get('impact_score', '')}"),
        meta_row("Next action", deal.get("next_action", "")),
    ])

    source = ""
    if deal.get("source_url"):
        source = (
            f'<p class="src"><a href="{_esc(deal["source_url"])}" target="_blank" '
            f'rel="noopener noreferrer">View original source: {_esc(deal.get("source_name") or "link")} ↗</a></p>'
        )

    prefill = f"{title} · {deal.get('org', '')}"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{_esc(title)} · Deal Radar · SAI Agency</title>
    <meta name="description" content="{_esc(desc)}" />
    <link rel="canonical" href="{_esc(url)}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="SAI Deal Radar" />
    <meta property="og:title" content="{_esc(title)}" />
    <meta property="og:description" content="{_esc(desc)}" />
    <meta property="og:url" content="{_esc(url)}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{_esc(title)}" />
    <meta name="twitter:description" content="{_esc(desc)}" />
    <link rel="stylesheet" href="/assets/deals.css" />
    <script type="application/ld+json">{_json_ld(deal, url)}</script>
  </head>
  <body>
    <main class="wrap detail">
      <p class="pipeline-note"><a href="/deals">← Deal Radar</a> · <a href="/">SAI Agency</a></p>
      <article class="deal prio-{_esc(deal.get('priority', 'medium'))}">
        <div class="top">
          <h1>{_esc(title)}</h1>
        </div>
        <p class="org">{_esc(org_line)}</p>
        <p class="desc">{_esc(deal.get('description', ''))}</p>
        <div class="detail-grid">{rows}</div>
        {source}
      </article>

      <section class="card interest">
        <h2>Pursue this deal with SAI Agency</h2>
        <p class="tagline">We help teams win grants, tenders and post-raise AI/ML builds. Tell us about your goal and we'll respond within one business day.</p>
        <form name="deal-interest" method="POST" action="/deals/{_esc(deal['id'])}.html?interest=1" data-netlify="true" netlify-honeypot="bot-field">
          <input type="hidden" name="form-name" value="deal-interest" />
          <input type="hidden" name="deal" value="{_esc(prefill)}" />
          <input type="hidden" name="deal_url" value="{_esc(deal.get('source_url', ''))}" />
          <p class="hp"><label>Leave this empty <input name="bot-field" /></label></p>
          <label for="pi-name">Name</label>
          <input id="pi-name" name="name" required autocomplete="name" />
          <label for="pi-email">Work email</label>
          <input id="pi-email" name="email" type="email" required autocomplete="email" />
          <label for="pi-company">Company (optional)</label>
          <input id="pi-company" name="company" autocomplete="organization" />
          <label for="pi-message">How can we help you win this?</label>
          <textarea id="pi-message" name="message"></textarea>
          <button class="btn" type="submit">Request support</button>
        </form>
      </section>

      <footer>
        <p>Sourced &amp; ARM-classified by the SAI Agency Deal Radar. Verify details at the source before acting. <a href="/deals.xml">Subscribe via RSS</a>.</p>
      </footer>
    </main>
  </body>
</html>
"""


def _deal_card(deal: Dict, site_url: str) -> str:
    tlabel = _TYPE_LABEL.get(deal.get("type", ""), deal.get("type", ""))
    meta = " · ".join(filter(None, [
        tlabel,
        _CAT_LABEL.get(deal.get("category", ""), "") if deal.get("category") != "ai_ml" else "",
        euro(deal.get("value_eur")) if deal.get("value_eur") else "",
        f"deadline {deal['deadline']}" if deal.get("deadline") else "",
    ]))
    return (
        f'<a class="deal prio-{_esc(deal.get("priority", "medium"))}" '
        f'href="/deals/{_esc(deal["id"])}" style="display:block;text-decoration:none;color:inherit;">'
        f'<div class="top"><h3>{_esc(deal.get("title", ""))}</h3></div>'
        f'<p class="org">{_esc(" · ".join(filter(None, [deal.get("org"), deal.get("city")])))}</p>'
        f'<p class="desc">{_esc((deal.get("description") or "")[:180])}</p>'
        f'<div class="meta"><span>{_esc(meta)}</span></div></a>'
    )


def render_country_page(country: str, deals: List[Dict], site_url: str = DEFAULT_SITE) -> str:
    slug = country_slug(country)
    url = f"{site_url}/country/{slug}"
    cats = sorted({_CAT_LABEL.get(d.get("category", ""), d.get("category", "")) for d in deals})
    desc = (
        f"{len(deals)} real AI/ML, €1-house/relocation and business-succession "
        f"opportunities in {country} — sourced, impact-scored and pipeline-classified by SAI Agency."
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"Opportunities in {country}",
        "description": desc,
        "url": url,
    }
    ld_json = json.dumps(ld, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    cards = "\n".join(_deal_card(d, site_url) for d in deals)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Opportunities in {_esc(country)} · SAI Agency Deal Radar</title>
    <meta name="description" content="{_esc(desc)}" />
    <link rel="canonical" href="{_esc(url)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="SAI Deal Radar" />
    <meta property="og:title" content="Opportunities in {_esc(country)} — Deal Radar" />
    <meta property="og:description" content="{_esc(desc)}" />
    <meta property="og:url" content="{_esc(url)}" />
    <meta name="twitter:card" content="summary" />
    <link rel="stylesheet" href="/assets/deals.css" />
    <script type="application/ld+json">{ld_json}</script>
  </head>
  <body>
    <main class="wrap">
      <p class="pipeline-note"><a href="/deals">← Deal Radar</a> · <a href="/countries">All countries</a> · <a href="/demo">Succession &amp; repopulation</a></p>
      <header><div class="masthead"><h1><span class="kicker">{_esc(country)}</span> · Opportunities</h1></div>
      <p class="tagline">{_esc(str(len(deals)))} sourced opportunities in {_esc(country)} — {_esc(", ".join(cats))}. Each links to its official source and a pre-filled enquiry form.</p></header>
      <section class="deals">
{cards}
      </section>
      <footer><p>Filtered live view: <a href="/deals?country={_esc(country)}">{_esc(country)} on the Deal Radar</a> · <a href="/deals.xml">RSS</a>. Verify details at the source before acting.</p></footer>
    </main>
  </body>
</html>
"""


def render_countries_index(groups: Dict[str, List[Dict]], site_url: str = DEFAULT_SITE) -> str:
    rows = "\n".join(
        f'<a class="deal" href="/country/{country_slug(c)}" style="display:flex;justify-content:space-between;text-decoration:none;color:inherit;">'
        f'<span><b>{_esc(c)}</b></span><span class="count">{len(ds)} opportunities</span></a>'
        for c, ds in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])) if c
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Opportunities by country · SAI Agency Deal Radar</title>
    <meta name="description" content="Browse AI/ML, €1-house/relocation and business-succession opportunities by country — SAI Agency Deal Radar." />
    <link rel="canonical" href="{site_url}/countries" />
    <link rel="stylesheet" href="/assets/deals.css" />
  </head>
  <body>
    <main class="wrap">
      <p class="pipeline-note"><a href="/deals">← Deal Radar</a> · <a href="/demo">Succession &amp; repopulation</a></p>
      <header><div class="masthead"><h1><span class="kicker">SAI Agency</span> · Opportunities by country</h1></div></header>
      <section class="deals">
{rows}
      </section>
    </main>
  </body>
</html>
"""


def render_sitemap(deals: List[Dict], site_url: str = DEFAULT_SITE, extra_paths: List[str] | None = None) -> str:
    urls = [
        (f"{site_url}/", "weekly", "1.0"),
        (f"{site_url}/deals", "daily", "0.9"),
        (f"{site_url}/demo", "weekly", "0.8"),
        (f"{site_url}/match", "weekly", "0.8"),
        (f"{site_url}/countries", "weekly", "0.7"),
    ]
    urls += [(f"{site_url}/{p}", "weekly", "0.8") for p in (extra_paths or [])]
    urls += [(deal_url(d, site_url), "weekly", "0.7") for d in deals]
    body = "\n".join(
        f"  <url>\n    <loc>{_esc(loc)}</loc>\n    <changefreq>{cf}</changefreq>\n    <priority>{pr}</priority>\n  </url>"
        for loc, cf, pr in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )


def export_site(dataset: Dict, base_dir: Path | str, site_url: str = DEFAULT_SITE) -> Dict:
    """Write per-deal pages + sitemap under ``base_dir`` (the site root)."""
    base = Path(base_dir)
    deals = dataset.get("deals", [])
    deals_dir = base / "deals"
    deals_dir.mkdir(parents=True, exist_ok=True)

    # Refresh: remove stale generated pages so deleted deals don't linger.
    existing = {p.name for p in deals_dir.glob("*.html")}
    written = set()
    for deal in deals:
        page = deals_dir / f"{deal['id']}.html"
        page.write_text(render_deal_page(deal, site_url), encoding="utf-8")
        written.add(page.name)
    for stale in existing - written:
        (deals_dir / stale).unlink()

    # --- Per-country landing pages (+ index) — SEO surface per geography ---
    groups: Dict[str, List[Dict]] = {}
    for d in deals:
        c = (d.get("country") or "").strip()
        if c:
            groups.setdefault(c, []).append(d)
    country_dir = base / "country"
    country_dir.mkdir(parents=True, exist_ok=True)
    existing_c = {p.name for p in country_dir.glob("*.html")}
    written_c = set()
    country_paths = []
    for country, cdeals in groups.items():
        slug = country_slug(country)
        (country_dir / f"{slug}.html").write_text(render_country_page(country, cdeals, site_url), encoding="utf-8")
        written_c.add(f"{slug}.html")
        country_paths.append(f"country/{slug}")
    for stale in existing_c - written_c:
        (country_dir / stale).unlink()
    (base / "countries.html").write_text(render_countries_index(groups, site_url), encoding="utf-8")

    sitemap = base / "sitemap.xml"
    sitemap.write_text(render_sitemap(deals, site_url, extra_paths=sorted(country_paths)), encoding="utf-8")
    return {
        "pages": len(written),
        "removed": len(existing - written),
        "country_pages": len(written_c),
        "sitemap": str(sitemap),
    }
