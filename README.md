# SAI Deal Radar

AI-agent-native opportunity radar: a continuously-refreshed, source-cited list of real **AI/ML grants, business succession, property / relocation schemes and venture vehicles** sourced worldwide. Every deal links to its official source; every surface is machine-readable.

→ **[Open the Deal Radar](https://sai-agency-deals-radar.netlify.app/deals)**  ·  [JSON dataset](https://sai-agency-deals-radar.netlify.app/deals.json)  ·  [RSS feed](https://sai-agency-deals-radar.netlify.app/deals.xml)  ·  [LLMs map](https://sai-agency-deals-radar.netlify.app/llms.txt)

---

## For end users

- **[Find your match](https://sai-agency-deals-radar.netlify.app/match)** — paste a business plan, get ranked deals.
- **[By country](https://sai-agency-deals-radar.netlify.app/countries)** — per-country landing pages (SEO).
- **[Weekly digest](https://sai-agency-deals-radar.netlify.app/deals)** — subscribe at the top of the radar.

## For AI agents + developers

The site is agent-discoverable by design. Every deal on `/deals.json` carries its own `impact_score`, evolved `arm_priority`, and a short `arm_rationale` explaining why it ranks there — so a buyer-side agent can reason about each opportunity, not just read the prose.

- **[INTEGRATE.md](./INTEGRATE.md)** — four consumable shapes (JSON · RSS · sitemap · agents manifest · llms.txt) and three ready-made integration patterns (agent retrieval, new-deal notifications, embed).
- **[TRANSPARENCY.md](./TRANSPARENCY.md)** — how deals are sourced, classified and ranked, with per-claim links to the code.
- **[SECURITY.md](./SECURITY.md)** — responsible-disclosure channel + security posture, citing the actual Netlify headers, KafCa `Bl` screen, and circuit breaker.
- **[CITATION.cff](./CITATION.cff)** — canonical citation metadata.

Agent-native entry points live at the usual addresses:

```
https://sai-agency-deals-radar.netlify.app/.well-known/agents.json
https://sai-agency-deals-radar.netlify.app/.well-known/ai.txt
https://sai-agency-deals-radar.netlify.app/.well-known/security.txt
https://sai-agency-deals-radar.netlify.app/llms.txt
https://sai-agency-deals-radar.netlify.app/llms-full.txt
```

Verify a deployment exposes all of them with:

```bash
pip install -e "agents/[dev]"
sai-agents-check https://sai-agency-deals-radar.netlify.app
```

## Architecture (one paragraph)

The agent suite in [`agents/`](./agents) runs a **KafCade** cascade: deals come from a curated seed ([`agents/data/deals_seed.json`](./agents/data/deals_seed.json)) plus optional RSS/Atom feeds, are normalised through a single pipeline that enforces a cited `source_url` and a deterministic SHA-1 ID, ARM-classified ([owner, stage, next action, priority](./agents/sai_agents/deals/arm.py)), and emitted as `DEAL_SIGNAL` events to the **KafCa** stream (event sourcing + impact tracking + blacklist/circuit-breaker). Each run's events compound into a durable per-genome JSONL trajectory under `SAI_TRAJECTORY_ROOT` — the **EvoMetaClaw** moat — which **EvoForge** (a deterministic (1+1)-ES hill-climber) and **EvoSkillOpt** (a UCB1 bandit over insight tags) consume to tilt the public `arm_priority` toward what's historically worked.

*Impact scores are never mutated by evolution — only the surfacing order — so the ranking cannot game its own fitness metric.*

## Why this is harder to copy than a registry

A competitor can mirror today's `/deals.json` in one HTTP GET. They **cannot** copy the per-genome trajectory history that produces the ordering — that history is the accumulation under `SAI_TRAJECTORY_ROOT`, written to by every agent run and compounded weekly by the [`evo-cycle`](./.github/workflows/evo-cycle.yml) GitHub Action. See `summary.trajectory_moat` in `/deals.json` for the current number. (Source: [`agents/sai_agents/evometaclaw/trajectory.py`](./agents/sai_agents/evometaclaw/trajectory.py).)

## Quickstart

```bash
# 1. Install the agent suite (Python 3.10+)
cd agents && pip install -e ".[dev]"

# 2. Regenerate the public dataset locally
python -m sai_agents.deals.generate            # writes ../deals.json + per-deal pages + sitemap

# 3. Run the full team (local mode, no Kafka required)
export SAI_TARGET_URL=https://example.com
python -m sai_agents.run_team

# 4. One self-compounding evolution cycle (team → evolve)
python -m sai_agents.run_cycle                 # trajectories under ~/.sai/trajectories

# 5. See how the flywheel is doing
python -m sai_agents.evo_report --markdown
```

Full CLI surface: `sai-run-team`, `sai-run-cycle`, `sai-evolve`, `sai-evo-report`, `sai-generate-deals`, `sai-agents-check`, `sai-service-tester`, `sai-ingest`, `sai-send-digest`, `sai-analytics`.

## Testing

```bash
cd agents && pytest -q
```

Public CI runs the same suite plus a full-site smoke-test and a lead-function smoke-test ([`.github/workflows/`](./.github/workflows/)).

## License

- **Code** — MIT ([LICENSE](./LICENSE) if present, else see `pyproject.toml`).
- **Dataset** (`/deals.json`, `/deals.xml`) — **CC BY 4.0**. Cite the per-deal `source_url` when quoting individual deals.
