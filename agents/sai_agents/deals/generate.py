"""CLI: run the KafCade deal cascade and export the site dataset.

    python -m sai_agents.deals.generate [OUTPUT_PATH]

Default OUTPUT_PATH is ``<repo-root>/deals.json`` so the Netlify site can fetch
``/deals.json`` directly. Also publishes each deal as a DEAL_SIGNAL evolution
event to KafCa (or the structured-log fallback).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sai_agents.config import get_settings
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.logging_setup import configure_logging, get_logger

log = get_logger("deals.generate")

# agents/sai_agents/deals/generate.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT = _REPO_ROOT / "deals.json"


async def _run(output: Path) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    pipeline = KafCadePipeline(settings=settings)
    return await pipeline.run(export_path=output)


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT
    result = asyncio.run(_run(output))
    print(
        json.dumps(
            {
                "deals": result["deals"],
                "published": result["published"],
                "high_impact": result["high_impact"],
                "output": str(output),
                "rss": result.get("rss_path"),
                "summary": result["dataset"]["summary"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
