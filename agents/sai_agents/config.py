"""Centralised, environment-driven configuration.

All runtime knobs are read from the environment so the same image runs in local
docker-compose, Fly.io, Railway, or a CI runner without code changes.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseModel):
    """Immutable runtime settings resolved from the environment."""

    # --- Identity ---
    service_name: str = Field(default="sai-agents")
    environment: str = Field(default="production")

    # --- Target under test (ServiceTester) ---
    target_url: str = Field(default="https://sai-agency-deals-radar.netlify.app")
    target_timeout_seconds: float = Field(default=10.0)

    # --- KafCa: Kafka event sourcing ---
    kafka_bootstrap_servers: str = Field(default="")
    kafka_topic: str = Field(default="claw-evolution-events")
    kafka_client_id: str = Field(default="sai-agents")
    kafka_enabled: bool = Field(default=False)

    # --- KafCa: Circuit breaker (Bl) ---
    breaker_failure_threshold: int = Field(default=5)
    breaker_reset_seconds: float = Field(default=30.0)

    # --- KafCa: Impact tracking (Im) ---
    impact_high_watermark: float = Field(default=0.7)

    # --- Observability ---
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=True)
    metrics_enabled: bool = Field(default=False)
    metrics_port: int = Field(default=9464)

    # --- Blacklist (Bl) ---
    blacklist_patterns: List[str] = Field(default_factory=list)

    # --- RRSS: live RSS/Atom deal feeds (opt-in) ---
    rss_feeds: List[str] = Field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Settings":
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        return cls(
            service_name=os.getenv("SAI_SERVICE_NAME", "sai-agents"),
            environment=os.getenv("SAI_ENV", "production"),
            target_url=os.getenv("SAI_TARGET_URL", "https://sai-agency-deals-radar.netlify.app"),
            target_timeout_seconds=float(os.getenv("SAI_TARGET_TIMEOUT", "10")),
            kafka_bootstrap_servers=bootstrap,
            kafka_topic=os.getenv("KAFKA_TOPIC", "claw-evolution-events"),
            kafka_client_id=os.getenv("KAFKA_CLIENT_ID", "sai-agents"),
            # Kafka is auto-enabled whenever a bootstrap server is provided,
            # unless explicitly disabled.
            kafka_enabled=_env_bool("KAFKA_ENABLED", bool(bootstrap)),
            breaker_failure_threshold=int(os.getenv("SAI_BREAKER_THRESHOLD", "5")),
            breaker_reset_seconds=float(os.getenv("SAI_BREAKER_RESET", "30")),
            impact_high_watermark=float(os.getenv("SAI_IMPACT_HIGH", "0.7")),
            log_level=os.getenv("SAI_LOG_LEVEL", "INFO"),
            log_json=_env_bool("SAI_LOG_JSON", True),
            metrics_enabled=_env_bool("SAI_METRICS_ENABLED", False),
            metrics_port=int(os.getenv("SAI_METRICS_PORT", "9464")),
            blacklist_patterns=_env_list("SAI_BLACKLIST_PATTERNS", []),
            rss_feeds=_env_list("SAI_RSS_FEEDS", []),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings (cached)."""
    return Settings.from_env()
