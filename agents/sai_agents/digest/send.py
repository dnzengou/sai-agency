"""CLI: build and send (or dry-run preview) the weekly deal digest.

    python -m sai_agents.digest.send [--dry-run] [--region R] [--limit N] [deals.json]

Reads the deal dataset (default: <repo-root>/deals.json), collects subscribers
(DIGEST_TO / SAI_LEAD_STORE / Netlify Forms API), builds the digest, and sends
via SMTP — or writes an HTML preview when SMTP is unconfigured or --dry-run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sai_agents.digest.builder import build_digest
from sai_agents.digest.sender import DigestSender, SMTPConfig
from sai_agents.digest.subscribers import collect_subscribers
from sai_agents.logging_setup import configure_logging, get_logger

log = get_logger("digest.send")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]

    region = None
    limit = 10
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--region" and i + 1 < len(argv):
            region = argv[i + 1]; i += 2
        elif argv[i] == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1]); i += 2
        else:
            positional.append(argv[i]); i += 1

    deals_path = Path(positional[0]) if positional else _REPO_ROOT / "deals.json"
    configure_logging("INFO", True)
    dataset = json.loads(deals_path.read_text(encoding="utf-8"))

    subject, html_body, text_body = build_digest(dataset, region=region, limit=limit)
    subscribers = collect_subscribers()

    config = SMTPConfig.from_env()
    preview = str(_REPO_ROOT / "digest-preview.html")
    if dry_run:
        config.host = ""  # force preview
    sender = DigestSender(config=config, preview_path=preview)
    result = sender.send(subscribers, subject, html_body, text_body)

    print(json.dumps({"subject": subject, "subscribers": len(subscribers),
                      "smtp_enabled": config.enabled, **result,
                      "preview": preview if not config.enabled else None}, indent=2))


if __name__ == "__main__":
    main()
