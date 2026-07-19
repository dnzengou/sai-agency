# SAI Agents — KafCa E+Im+Bl suite (evolves evo-metaclaw)

Production-ready, reusable agent suite for **SAI Agency**:

- **Marketing** — positioning, content, acquisition insights
- **Sales + GTM** — pipeline, CTA, productised-offer recommendations
- **Outreach** — outbound comms cadence (email + LinkedIn) + persona-specific
  templates for the SAI Agency ICP; Bl-screens every ICP input against
  jailbreak/injection signatures before any copy is generated
- **VulnRedTeam** — passive security-header posture + input red-teaming
- **ServiceTester** — continuous feedback loop; probes the live site and emits
  **evolution-grade signals** (insights, recommendations, fitness scores)
- **DealSourcing** — the **KafCade** cascade: sources real opportunities from
  **RRSS** sources, ARM-classifies them, and emits `DEAL_SIGNAL` events
- **Orchestrator** — runs the whole team, threads live findings downstream, and
  publishes every result to the KafCa event stream

## Deal Radar (KafCade · RRSS · ARM)

The suite ships a working **deal-sourcing** feature that powers the site's
`/deals` page.

- **KafCade** — a cascade of KafCa stages: `RRSS fetch → normalize → Bl screen →
  dedupe → ARM classify (+impact) → publish → export`.
- **RRSS** (Redes/RSS Sources) — a pluggable source registry. The bundled source
  reads a curated dataset of **real, publicly-sourced** grants, tenders,
  accelerators, and funding rounds across Southern Europe and the Nordics (each
  deal carries a real `source_url`). Add RSS/social/procurement feeds by
  implementing `DealSource.fetch()`.
- **ARM** (Account & Relationship Management) — each deal is enriched with an ARM
  pipeline stage, owner queue, next action, priority, and impact score.

```bash
# Run the cascade: publish DEAL_SIGNAL events + write the site dataset
python -m sai_agents.deals.generate            # writes <repo-root>/deals.json + deals.xml
python -m sai_agents.deals.generate out.json   # or a chosen path (RSS -> out.xml)
```

The web app fetches `/deals.json` and renders a filterable, ARM-classified
dashboard (`deals.html` + `/assets/deals.{js,css}`) with a lead-gen funnel
(deal-alert + pursue-deal Netlify Forms, CSV export, shareable URL filters) and
an RRSS feed at `/deals.xml`.

## KafCa

**KafCa = Kafka for Event sourcing (E) + Impact tracking (Im) + Bl (Blacklist + Circuit Breaker) for safe self-evolution.**

- **Event Sourcing (E)** — every feedback, health check, insight, and evolution
  signal is published to the append-only Kafka topic `claw-evolution-events`.
- **Impact tracking (Im)** — every event carries a quantitative `impact_score`
  (0..1). High-impact events are surfaced for `evo-metaclaw` prioritisation.
- **Bl** — a **Blacklist** rejects jailbreak/injection-style input before it can
  contaminate the loop, and a **Circuit Breaker** halts publishing on repeated
  failures (prevents bad evolution loops). Mirrors `evolved-skill-opt` safety
  patterns.
- **Evolve evo-metaclaw** — `ServiceTester` + `KafkaEventPublisher` produce
  clean, structured `EvolutionEvent`s (with `FitnessScore`s) that `evo-metaclaw`
  / `evolved-skill-opt` can consume directly for population-based evolution.

## EvoMetaClaw — the strategic moat (trajectory flywheel)

Every accepted `EvolutionEvent` is **appended to a durable, per-genome JSONL
trajectory** (`sai_agents.evometaclaw.TrajectoryStore`). Wired directly into the
KafCa publisher — no extra config; the flywheel is ON by default.

**Why this is the moat**: OpenClaw can copy a skill registry. They cannot copy
SkillOpt-powered self-evolving bots without rebuilding the entire training
paradigm *and* accumulating the trajectory data. Every run leaves durable
ground-truth signal that population-based evolution consumes — the moat
compounds with usage.

| Variable | Default | Purpose |
|---|---|---|
| `SAI_TRAJECTORY_ROOT` | `~/.sai/trajectories` | Where JSONL trajectories persist |
| `SAI_TRAJECTORY_ENABLED` | `true` | Set to `false` to disable persistence |

Fail-safe: disk errors are logged and swallowed; a broken FS never sinks the
live agents. Genomes are auto-partitioned (`{genome}.jsonl` per fitness
lineage), and a companion `{genome}._generations.jsonl` records fitness bumps
so evo-metaclaw can slice by generation in O(1).

## Install

```bash
pip install -e .                 # core (pydantic + structlog)
pip install -e ".[kafka]"        # + aiokafka transport
pip install -e ".[metrics]"      # + prometheus-client
pip install -e ".[all]"          # everything incl. dev/test
```

The package **degrades gracefully**: with no Kafka configured (or `aiokafka`
absent) it falls back to durable structured logging, so events are never lost
and every command still runs anywhere.

## Run

```bash
# Full orchestrated team against the live site:
python -m sai_agents.run_team

# ServiceTester feedback loop only (publishes an evolution signal):
python -m sai_agents.service_testers.service_tester_agent

# Lead ingest endpoint (target for the Netlify lead-bridge KAFCA_WEBHOOK_URL):
python -m sai_agents.ingest.server          # GET /health, POST /ingest -> KafCa
```

Console scripts are also installed: `sai-run-team`, `sai-service-tester`,
`sai-generate-deals`, `sai-ingest`.

### With a live Kafka broker

```bash
docker compose up --build           # Kafka + Zookeeper + agents
# or point at your own broker:
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_ENABLED=true
python -m sai_agents.run_team
```

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `SAI_TARGET_URL` | `https://sai-agency.netlify.app` | Site the ServiceTester probes |
| `SAI_TARGET_TIMEOUT` | `10` | Probe timeout (s) |
| `KAFKA_BOOTSTRAP_SERVERS` | *(empty)* | Kafka brokers; enables Kafka when set |
| `KAFKA_TOPIC` | `claw-evolution-events` | Event-sourcing topic |
| `KAFKA_ENABLED` | auto | Force-enable/disable Kafka |
| `SAI_BREAKER_THRESHOLD` | `5` | Circuit-breaker failure threshold |
| `SAI_BREAKER_RESET` | `30` | Circuit-breaker cooldown (s) |
| `SAI_IMPACT_HIGH` | `0.7` | High-impact watermark for evo-metaclaw |
| `SAI_BLACKLIST_PATTERNS` | *(empty)* | Extra regex signatures, comma-separated |
| `SAI_LOG_LEVEL` / `SAI_LOG_JSON` | `INFO` / `true` | Structured logging |
| `SAI_METRICS_ENABLED` / `SAI_METRICS_PORT` | `false` / `9464` | Prometheus |

## Evolution signal contract

Every event is an `EvolutionEvent` (see `sai_agents/models.py`) published as JSON
to `claw-evolution-events`, keyed by `source_agent` (preserves per-agent
ordering). Consume from `evo-metaclaw` / `evolved-skill-opt`; the schema is
additive and versioned (`schema_version`).

## Test

```bash
pip install -e ".[dev]"
pytest -q
```

## Deploy

- **Site** (`sai-agency.netlify.app`) — Netlify auto-deploys the static site.
- **Agents** — deploy this container to Fly.io / Railway / any container host.
  See [`sai-agents-for-sai-agency.md`](./sai-agents-for-sai-agency.md).
