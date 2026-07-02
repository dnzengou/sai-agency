# SAI Agents — Integration Guide for `sai-agency`

Tailored deployment guide for the [`dnzengou/sai-agency`](https://github.com/dnzengou/sai-agency)
repo and its Netlify site `https://sai-agency.netlify.app`.

## What this adds

A reusable, production-hardened agent suite (KafCa E+Im+Bl) that:

- Continuously **health-checks the live Netlify site** and generates prioritised,
  actionable insights (availability, latency, security headers, GTM, marketing).
- Emits **evolution-grade signals** (with fitness scores) to a Kafka event
  stream for `evo-metaclaw` / `evolved-skill-opt` self-evolution.
- Is **safe by construction**: blacklist for jailbreak/injection input + circuit
  breaker that halts publishing on repeated failures.

## Layout

```
agents/
├── sai_agents/                # the Python package (importable, testable)
│   ├── agents/                # Marketing, Sales+GTM, VulnRedTeam
│   ├── service_testers/       # ServiceTester feedback loop
│   ├── kafca/                 # Blacklist, CircuitBreaker, Impact, Publisher
│   ├── orchestrator.py        # full-team runner
│   └── run_team.py            # CLI entrypoint
├── Dockerfile
├── docker-compose.yml         # Kafka + Zookeeper + agents (local prod-like)
├── pyproject.toml
└── README.md
```

The site itself (`index.html`, `assets/`, `netlify.toml`) is unchanged except
for added security-response headers in `netlify.toml` (recommended by the
VulnRedTeam agent).

## Deploy the site (Netlify)

No action needed — Netlify auto-deploys `https://sai-agency.netlify.app` on push
to the default branch. The added `netlify.toml` security headers apply on the
next deploy.

## Deploy the agents (recommended: Fly.io — same pattern as picoclaw-server)

The Python agents run as a separate container service. Netlify hosts the static
site; the agents run wherever containers run.

```bash
cd agents

# Option A — Fly.io (matches your existing FLY_API_TOKEN / CI pattern)
fly launch --no-deploy            # generates fly.toml (first time only)
fly secrets set KAFKA_BOOTSTRAP_SERVERS=... KAFKA_ENABLED=true
fly deploy --remote-only

# Option B — local prod-like stack with Kafka
docker compose up --build

# Option C — no Kafka; structured-log fallback (still fully functional)
pip install -e . && python -m sai_agents.run_team
```

### Netlify Functions / AI Gateway (lighter, optional)

For on-site capabilities you can expose a thin Netlify Function that calls the
agent container's API, or run the lightweight `ServiceTester` on a schedule and
surface results in the site. Heavy lifting (full team, Kafka) belongs in the
container service.

## Run the feedback loop

```bash
cd agents
pip install -e .
python -m sai_agents.service_testers.service_tester_agent   # single probe + signal
python -m sai_agents.run_team                                # full orchestrated team
```

It health-checks the live Netlify site, runs the GTM/marketing/security agents
over the live context, and outputs prioritised insights + a deployment
`FitnessScore` for continuous improvement and evolution.

## Feeding evo-metaclaw

Point a Kafka consumer (or `evo-metaclaw` / `evolved-skill-opt`) at topic
`claw-evolution-events`. Each message is a JSON `EvolutionEvent` with
`impact_score`, `insights`, `recommendations`, and (for tester/orchestrator
events) a `fitness` block — ready for population-based skill evolution.

## Why this fits SAI Agency

- **Marketing & Sales+GTM** — acquire clients for custom agents, automation, ML.
- **VulnRedTeam** — hardens the agency site and any AI deliverables.
- **ServiceTester** — closed feedback loop from the live site → rapid iteration.
- **Reusable** — drop the `sai_agents/` package into any future client repo.
