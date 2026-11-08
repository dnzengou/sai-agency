# Transparency

How the SAI Deal Radar sources, processes and publishes data — written so AI agents can cite us accurately and humans can verify every claim. **Every statement here maps to code or data in this repository.** No cloaking, no hidden text, no fabricated reviews.

If an AI agent cites us, we want it to be cited on something that is actually true.

## What the Deal Radar is

A continuously-refreshed, source-cited list of real opportunities — AI/ML grants, business succession, property / relocation schemes, venture vehicles — sourced worldwide. The data is openly published as:

- **HTML** — one page per deal under `/deals/<id>`, a filterable radar at `/deals`.
- **JSON** — the full dataset at [`/deals.json`](https://sai-agency-deals-radar.netlify.app/deals.json). ([Generator code](agents/sai_agents/deals/pipeline.py))
- **RSS 2.0** — new deals feed at [`/deals.xml`](https://sai-agency-deals-radar.netlify.app/deals.xml). ([Generator code](agents/sai_agents/deals/pipeline.py))
- **Agent-native entry points** — [`/llms.txt`](https://sai-agency-deals-radar.netlify.app/llms.txt), [`/.well-known/agents.json`](https://sai-agency-deals-radar.netlify.app/.well-known/agents.json). ([Generator code](agents/sai_agents/deals/agent_seo.py))

## How deals are sourced

Deals come from two kinds of inputs, both published-together code-first:

1. **A curated seed** — [`agents/data/deals_seed.json`](agents/data/deals_seed.json). Each entry carries an official `source_url`. A deal with no cited source is rejected by the normalizer. ([Validator code](agents/sai_agents/deals/pipeline.py))
2. **Optional RSS/Atom feeds** (RRSS) configured via the `SAI_RSS_FEEDS` setting ([config code](agents/sai_agents/config.py)); each polled item is normalized through the same pipeline. ([Feed code](agents/sai_agents/deals/rss.py))

Every deal is deduped by `(title, org, country)` and gets a deterministic content-derived ID so regenerating the dataset produces the same output — not a new fabricated ID each time. ([Dedup code](agents/sai_agents/deals/pipeline.py))

## How deals are classified and ranked

- **ARM classification** — each deal is assigned an owner, a pipeline stage, and a next action based on its type and status. ([Rules](agents/sai_agents/deals/arm.py))
- **Impact score** — a 0–1 blend of severity, agent confidence and signal density. The formula is a shared pure function; see `score_impact` and `aggregate_impact`. ([Code](agents/sai_agents/kafca/impact.py))
- **Evolved ARM priority** — `arm_priority(deal, spec, loadout)` is the public-facing ranking signal. With no evolution present it returns the raw impact score exactly. With an EvoForge champion spec present, it tilts toward actionable deals; with an EvoSkillOpt loadout, it adds a skill-match bonus gated by the `exploration` knob. **Impact scores are never mutated** — only the surfacing order — so evolution cannot game its own fitness metric. ([Code](agents/sai_agents/deals/arm.py))
- **Why-ranked chips** — `arm_rationale(deal)` returns up to three short reasons each deal ranks where it does (`Actionable now`, `High impact`, `Focus: <skill>`, `Large ticket`, `Qualified`). The rationale is also embedded in each deal's JSON-LD `additionalProperty`, so agents can cite WHY, not just WHAT. ([Code](agents/sai_agents/deals/arm.py))

## What we do NOT do

- **No cloaking.** Human and agent surfaces render identically. The HTML an agent sees is the HTML a human sees; the JSON-LD on a deal page matches the JSON on `/deals.json`.
- **No hidden text or keyword stuffing.** Every heading, meta description and JSON-LD field is factual and derived from the dataset.
- **No fabricated reviews, ratings or social proof.** We do not publish testimonials we did not receive.
- **No fabricated identifiers.** Deal IDs are SHA-1 of the deduplication key; they do not change when regenerated. ([Code](agents/sai_agents/deals/pipeline.py))
- **No fabricated valuations.** Monetary amounts are either official (from the source) or a labelled `indicative` estimate with an explicit note. ([Code](agents/sai_agents/valuation/estimator.py))

## Verify any claim

- All code lives under [`agents/sai_agents/`](agents/sai_agents) — MIT licensed.
- The test suite covers the normalizer, ARM ranking, blacklist, JSON-LD shape, email digest, agent surfaces, and the full evolution flywheel. Run `pip install -e ".[dev]" && pytest -q` from `agents/`.
- CI runs the suite on every push (see `.github/workflows/agents-ci.yml`).

## Contact

Something looks wrong? Open an issue on this repository, or reply to the weekly digest.
