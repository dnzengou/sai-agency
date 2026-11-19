"""CLI: push the current Deal Radar snapshot to ntfy.

    python -m sai_agents.digest.ntfy_send [deals.json] [--dry-run]

Reads ``deals.json`` (repo root by default), groups the open/upcoming deals
into the fixed ntfy topic taxonomy, and POSTs one notification per non-empty
topic. Prints a JSON receipt. Safe to schedule: ``--dry-run`` writes a preview
JSON so nothing is silently lost.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sai_agents.digest.ntfy import NtfyConfig, NtfyPublisher
from sai_agents.logging_setup import configure_logging, get_logger

log = get_logger("digest.ntfy_send")

# agents/sai_agents/digest/ntfy_send.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INPUT = _REPO_ROOT / "deals.json"


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    dry_run = "--dry-run" in args
    paths = [a for a in args if not a.startswith("--")]
    src = Path(paths[0]) if paths else _DEFAULT_INPUT
    if not src.exists():
        print(f"error: {src} not found. Run sai-generate-deals first.", file=sys.stderr)
        sys.exit(2)

    configure_logging("INFO", True)
    dataset = json.loads(src.read_text(encoding="utf-8"))
    cfg = NtfyConfig.from_env()
    publisher = NtfyPublisher(
        config=cfg,
        preview_path=str(_REPO_ROOT / "ntfy-preview.json"),
    )
    result = publisher.publish(dataset, dry_run=dry_run)
    receipt = {k: result[k] for k in ("topics", "sent", "dry_run", "failed")}
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
