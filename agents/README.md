# SAI Agents — KafCa E+Im+Bl suite (evolves evo-metaclaw)

Production-ready, reusable agent suite for **SAI Agency**:

- **Marketing** — positioning, content, acquisition insights
- **Sales + GTM** — pipeline, CTA, productised-offer recommendations
- **VulnRedTeam** — passive security-header posture + input red-teaming
- **ServiceTester** — continuous feedback loop; probes the live site and emits
  **evolution-grade signals** (insights, recommendations, fitness scores)
- **Orchestrator** — runs the whole team, threads live findings downstream, and
  publishes every result to the KafCa event stream

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
```

Console scripts are also installed: `sai-run-team`, `sai-service-tester`.

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
