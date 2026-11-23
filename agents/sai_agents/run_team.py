"""CLI entrypoint: run the full orchestrated team once and print the summary.

    python -m sai_agents.run_team

Honours all environment configuration (see ``sai_agents.config.Settings``).
"""

from __future__ import annotations

import asyncio
import json

from sai_agents.config import get_settings
from sai_agents.logging_setup import configure_logging, get_logger
from sai_agents.metrics import maybe_start_metrics_server
from sai_agents.orchestrator import OrchestratorTeam

log = get_logger("run_team")


async def _run() -> dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    maybe_start_metrics_server(settings.metrics_enabled, settings.metrics_port)
    log.info(
        "run_team.start",
        service=settings.service_name,
        target=settings.target_url,
        kafka_enabled=settings.kafka_enabled,
    )
    team = OrchestratorTeam(settings)
    return await team.run()


def main() -> None:
    summary = asyncio.run(_run())
    # Print a compact, machine-readable summary for CI / evo-metaclaw pipelines.
    print(
        json.dumps(
            {
                "events_published": summary["events_published"],
                "team_fitness": summary["team_fitness"],
                "high_impact_events": summary["high_impact_events"],
                "kafka_active": summary["kafka_active"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
