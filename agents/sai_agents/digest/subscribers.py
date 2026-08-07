"""Collect deal-alert subscribers from available sources.

Priority-merged, de-duplicated by email:
  1. DIGEST_TO           — explicit comma-separated list (testing / manual).
  2. SAI_LEAD_STORE      — NDJSON lead store, rows where form == "deal-alerts".
  3. Netlify Forms API   — GET submissions for NETLIFY_ALERTS_FORM_ID with
                           NETLIFY_API_TOKEN.

Each subscriber is ``{"email": str, "region": str|None}``.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from sai_agents.logging_setup import get_logger

log = get_logger("digest.subscribers")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


def from_env_list(raw: Optional[str]) -> List[Dict]:
    if not raw:
        return []
    return [{"email": e.strip(), "region": None} for e in raw.split(",") if _valid(e)]


def from_lead_store(path: Optional[str]) -> List[Dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    out: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("form") == "deal-alerts" and _valid(rec.get("email", "")):
            out.append({"email": rec["email"].strip(), "region": rec.get("region")})
    return out


def from_netlify(
    token: Optional[str],
    form_id: Optional[str],
    fetcher: Optional[Callable[[str, Dict[str, str]], str]] = None,
) -> List[Dict]:
    if not (token and form_id):
        return []
    url = f"https://api.netlify.com/api/v1/forms/{form_id}/submissions?per_page=1000"
    fetch = fetcher or _default_fetch
    try:
        body = fetch(url, {"Authorization": f"Bearer {token}"})
        subs = json.loads(body)
    except Exception as exc:
        log.error("digest.netlify.fetch_failed", error=str(exc))
        return []
    out: List[Dict] = []
    for s in subs if isinstance(subs, list) else []:
        data = s.get("data", s) if isinstance(s, dict) else {}
        email = (data.get("email") or "").strip()
        if _valid(email):
            out.append({"email": email, "region": data.get("region")})
    return out


def _default_fetch(url: str, headers: Dict[str, str], timeout: float = 15.0) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def collect_subscribers(
    env: Optional[Dict[str, str]] = None,
    netlify_fetcher: Optional[Callable[[str, Dict[str, str]], str]] = None,
) -> List[Dict]:
    env = env if env is not None else dict(os.environ)
    merged: List[Dict] = []
    merged += from_env_list(env.get("DIGEST_TO"))
    merged += from_lead_store(env.get("SAI_LEAD_STORE"))
    merged += from_netlify(env.get("NETLIFY_API_TOKEN"), env.get("NETLIFY_ALERTS_FORM_ID"), netlify_fetcher)

    seen: set = set()
    unique: List[Dict] = []
    for s in merged:
        key = s["email"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    log.info("digest.subscribers.collected", count=len(unique))
    return unique
