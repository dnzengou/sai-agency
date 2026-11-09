# Security

## Reporting a vulnerability

If you believe you have found a security issue in the SAI Deal Radar — the static site, the agent suite, the KafCa event stream, or the Netlify functions — please report it privately through the **GitHub security advisory** for this repository:

<https://github.com/dnzengou/sai-agency/security/advisories/new>

Please include:
- A description of the issue and its impact.
- Steps to reproduce (or a proof-of-concept URL).
- Any suggested mitigation.

We acknowledge receipt within 72 hours and aim to publish a fix (or a public disclosure timeline) within 14 days.

## Security posture — what the repository actually ships

Every claim below maps to a file in this repository. No marketing.

### Transport + browser hardening

The production site ships a conservative Content-Security-Policy plus strict HTTPS, no-sniff, no-frames and cross-origin-safe referrer policy. See [`netlify.toml`](netlify.toml) (the `[[headers]]` block).

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

No inline event handlers. All JSON-LD is in `<script type="application/ld+json">` (non-executable) with explicit escaping of `<`, `>` and `&` so a value containing `</script>` cannot break out of the script element. See `_json_ld` in [`agents/sai_agents/deals/site.py`](agents/sai_agents/deals/site.py).

### Input hygiene (KafCa `Bl`)

Every event that reaches the Kafka publisher is screened by a configurable blacklist before it can influence evolution — jailbreak / injection / secret patterns are blocked, with the matched pattern logged. See [`agents/sai_agents/kafca/blacklist.py`](agents/sai_agents/kafca/blacklist.py) and the test suite.

A circuit breaker wraps every publish; on repeated failure it opens and refuses writes until a reset window elapses, so a broken Kafka cannot spin a bad evolution loop. See [`agents/sai_agents/kafca/circuit_breaker.py`](agents/sai_agents/kafca/circuit_breaker.py).

### Fail-safe I/O

The durable trajectory store, EvoForge population, and EvoSkillOpt skill table all treat disk errors as warnings — never raises that sink the live agents. See [`agents/sai_agents/evometaclaw/trajectory.py`](agents/sai_agents/evometaclaw/trajectory.py), [`agents/sai_agents/evoforge/forge.py`](agents/sai_agents/evoforge/forge.py), [`agents/sai_agents/evoskillopt/optimizer.py`](agents/sai_agents/evoskillopt/optimizer.py).

### Secrets

No secrets are committed. The lead-ingest webhook (CRM forwarding) reads `CRM_WEBHOOK_URL` and `CRM_WEBHOOK_TOKEN` from the environment; omitting them disables forwarding without disabling the rest of the system. See [`agents/sai_agents/ingest/crm.py`](agents/sai_agents/ingest/crm.py).

### Supply chain

Runtime dependencies are intentionally minimal: `pydantic>=2.5` and `structlog>=23.1`. Optional extras (`aiokafka`, `prometheus-client`) fail open — the system runs without them in a structured-log local mode. See [`agents/pyproject.toml`](agents/pyproject.toml).

## Scope

- **In scope:** this repository (`dnzengou/sai-agency`) — the static site under the repository root and the Python package under `agents/`.
- **Out of scope:** third-party deal sources we link to (their security posture is their own).

## Credit

Valid, actionable reports are credited in the release notes unless the reporter asks otherwise.
