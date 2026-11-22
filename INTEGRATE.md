# Integrate with SAI Deal Radar

How to consume the Deal Radar from your own system, product, or agent — without screen-scraping, without an API key, without a vendor lock-in. Every endpoint below is **production-live**, generated deterministically from the same source data humans see.

> If you build an AI assistant or agent-flow that surfaces deals to a user, this is the contract.

## The four shapes you can consume

| Shape | URL | When to pick it |
| --- | --- | --- |
| **JSON** (recommended for agents) | [`/deals.json`](https://sai-agency-deals-radar.netlify.app/deals.json) | Full dataset + per-deal `arm_priority`, `arm_rationale`, `impact_score` |
| **RSS 2.0** (new-deal notifications) | [`/deals.xml`](https://sai-agency-deals-radar.netlify.app/deals.xml) | Poll or subscribe for new listings |
| **Sitemap** (crawlers) | [`/sitemap.xml`](https://sai-agency-deals-radar.netlify.app/sitemap.xml) | URL inventory for search / AI indexers |
| **Agent manifest** | [`/.well-known/agents.json`](https://sai-agency-deals-radar.netlify.app/.well-known/agents.json) | Programmatic self-description of capabilities + endpoints |
| **LLMs map** | [`/llms.txt`](https://sai-agency-deals-radar.netlify.app/llms.txt) | Markdown curation an LLM can ingest |

The dataset is licensed **CC BY 4.0** — use it, cite the source URL on each deal.

## The JSON shape

```jsonc
{
  "generated_at": "2026-11-08T05:42:00Z",
  "service": "sai-agents",
  "schema_version": 1,
  "summary": {
    "total_deals": 122,
    "open_or_upcoming": 71,
    "total_pipeline_value_eur": 902550660.0,
    "countries": ["Australia", "Austria", ...],
    "regions": ["Canada", "DACH", "East Africa", ...],
    "categories": ["ai_ml", "repopulation", "succession", "venture"],
    "evolved_order": false,           // true when EvoForge is driving order
    "arm": {
      "by_arm_stage": { "qualified": 70, "prospect": 37, "lost": 15 },
      "by_owner":     { "sales_gtm": 61, "marketing": 34, ... },
      "portfolio":    {
        "business":  { "count": 15, "value_eur": 0,         "open": 15, "avg_impact": 0.59 },
        "property":  { "count": 19, "value_eur": 7,         "open": 19, "avg_impact": 0.46 },
        "ai_deals":  { "count": 63, "value_eur": 850978660, "open": 36, "avg_impact": 0.68 },
        "ventures":  { "count": 25, "value_eur": 51575000,  "open":  1, "avg_impact": 0.55 }
      },
      "next_action_queue": [ { "action": "...", "count": 21 }, ... ]
    }
  },
  "deals": [
    {
      "id": "0031be5e66bd11f3",   // deterministic SHA-1 of (title, org, country)
      "title": "...",
      "org":   "...",
      "country": "Spain", "region": "Southern Europe", "city": "Madrid",
      "sector": "AI/ML",
      "type":     "grant",             // one of: grant|public_tender|accelerator|
                                       //         funding_round|partnership|rfp|
                                       //         property_scheme|business_succession|
                                       //         venture
      "category": "ai_ml",             // one of: ai_ml|repopulation|succession|venture
      "value_eur": 60000000,           // null when unknown
      "stage":    "closed",            // open|upcoming|closed|announced
      "deadline": "2025-07-01",
      "source_url":  "https://one.gob.es/...",
      "source_name": "one.gob.es",
      "description": "...",            // factual, ~1 sentence
      "confidence":  0.7,

      "arm_stage":    "lost",          // prospect|qualified|engaged|proposal|won|lost
      "owner":        "sales_gtm",
      "next_action":  "...",
      "priority":     "medium",        // low|medium|high|critical
      "impact_score": 0.68,            // never changed by evolution
      "arm_priority": 0.68,            // ordering signal; == impact_score when unevolved
      "arm_rationale": ["Actionable now", "High impact"]
    }
  ]
}
```

All field semantics are enforced by [`Deal` in `models.py`](agents/sai_agents/models.py).

## Three ready-made integrations

### 1. Agent / LLM — "find deals matching X"

Point your retrieval at `/deals.json` (one HTTPS GET, ~130 KB) or the richer per-deal pages (`/deals/<id>` carries typed JSON-LD: `Grant`, `Offer`, `InvestmentOrDeposit`, with `applicationDeadline`, `funder`, `areaServed`, `MonetaryAmount`).

```python
import urllib.request, json

with urllib.request.urlopen("https://sai-agency-deals-radar.netlify.app/deals.json") as r:
    data = json.load(r)

open_grants_eu = [d for d in data["deals"]
                  if d["type"] == "grant"
                  and d["stage"] in ("open", "upcoming")
                  and d["region"] == "EU"]
```

Each deal already carries its own why-ranked rationale — surface it to the user so they can see the model's reasoning.

### 2. Notifications — new deals in a region

Subscribe your inbox or a webhook to the RSS feed:

```
https://sai-agency-deals-radar.netlify.app/deals.xml
```

Or wire a server-side poller (every deal has a deterministic `id`, so dedup is trivial).

### 3. Embed — a live radar in another site

The whole SPA is one static page you can iframe (same-origin or set `X-Frame-Options: ALLOWALL` if you host your own build):

```html
<iframe src="https://sai-agency-deals-radar.netlify.app/deals"
        style="width:100%;height:100vh;border:0;" loading="lazy"></iframe>
```

Or just render the JSON — the shape is documented above.

## Lead capture (optional, server-to-server)

The Deal Radar accepts leads via two Netlify Forms (`deal-alerts`, `deal-interest`) and emits a `LEAD_SIGNAL` KafCa event on each submission. If you run your own SAI agent stack:

- Point your Netlify webhook at `agents/sai_agents/ingest/server.py` (POST `/ingest`), which normalizes the submission and writes it to a local lead store.
- Set `CRM_WEBHOOK_URL` + `CRM_WEBHOOK_TOKEN` to forward normalised leads to your CRM. Omitting them disables forwarding; nothing else changes.

See [`agents/sai_agents/ingest/crm.py`](agents/sai_agents/ingest/crm.py).

## Rate limits / etiquette

There is no API key and no hard rate limit. The site is static. Please:
- Cache responses for at least 60 seconds client-side.
- Set an identifying `User-Agent` on server-to-server fetches (`YourApp/1.0; +https://your.site`).
- If you're an AI crawler, read `/.well-known/agents.json` first — it lists every entry point so you can skip the HTML.

## Changing shape

The dataset is versioned via `schema_version` (currently `1`). Additive changes keep the version; a breaking change bumps it. Field removal is announced in the release notes.
