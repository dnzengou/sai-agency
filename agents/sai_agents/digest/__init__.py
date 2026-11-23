"""Weekly email digest — turn the sourced deals into an actual email that ships.

Composes an HTML+text digest from the Deal Radar dataset, collects subscribers
(NDJSON lead store / Netlify Forms API / explicit list), and sends via SMTP —
with a lossless dry-run preview when no SMTP is configured.
"""

from sai_agents.digest.builder import build_digest, select_deals
from sai_agents.digest.sender import DigestSender, SMTPConfig
from sai_agents.digest.subscribers import collect_subscribers

__all__ = [
    "build_digest",
    "select_deals",
    "DigestSender",
    "SMTPConfig",
    "collect_subscribers",
]
