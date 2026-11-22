"""Optional Prometheus metrics.

Import-safe whether or not ``prometheus-client`` is installed. When absent, all
metric operations become cheap no-ops so call sites never need to guard.
"""

from __future__ import annotations

from sai_agents.logging_setup import get_logger

log = get_logger("metrics")

try:  # optional dependency
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROM_AVAILABLE = False


class _NoopMetric:
    def labels(self, *_args, **_kwargs) -> "_NoopMetric":
        return self

    def inc(self, *_args, **_kwargs) -> None:  # noqa: D401
        pass

    def set(self, *_args, **_kwargs) -> None:
        pass

    def observe(self, *_args, **_kwargs) -> None:
        pass


if _PROM_AVAILABLE:
    EVENTS_PUBLISHED = Counter(
        "sai_events_published_total",
        "Events published to the KafCa stream",
        ["event_type", "source_agent"],
    )
    EVENTS_BLOCKED = Counter(
        "sai_events_blocked_total",
        "Events rejected by blacklist or circuit breaker",
        ["reason"],
    )
    AGENT_RUNS = Counter(
        "sai_agent_runs_total", "Agent runs", ["agent", "ok"]
    )
    IMPACT_GAUGE = Gauge(
        "sai_last_impact_score", "Last aggregate impact score", ["agent"]
    )
    RUN_LATENCY = Histogram(
        "sai_agent_run_seconds", "Agent run latency (seconds)", ["agent"]
    )
else:  # pragma: no cover
    EVENTS_PUBLISHED = _NoopMetric()
    EVENTS_BLOCKED = _NoopMetric()
    AGENT_RUNS = _NoopMetric()
    IMPACT_GAUGE = _NoopMetric()
    RUN_LATENCY = _NoopMetric()


def maybe_start_metrics_server(enabled: bool, port: int) -> bool:
    if not enabled:
        return False
    if not _PROM_AVAILABLE:
        log.warning("metrics.unavailable", hint="install extra '[metrics]'")
        return False
    start_http_server(port)  # pragma: no cover - needs open port
    log.info("metrics.serving", port=port)  # pragma: no cover
    return True  # pragma: no cover
