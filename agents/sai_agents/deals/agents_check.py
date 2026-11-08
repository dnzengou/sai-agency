"""agents_check — validate that a deployed site exposes the agent surfaces.

    python -m sai_agents.deals.agents_check [URL]

Default URL is the production Deal Radar. Checks:
  * The dataset endpoint (/deals.json) returns valid JSON with the documented
    schema_version and at least one deal.
  * /llms.txt and /.well-known/agents.json are reachable and parseable.
  * robots.txt names the major AI crawlers.
  * /sitemap.xml lists the agent entry points.

Exits non-zero on any failure, so it slots into CI or an uptime monitor. No
runtime deps beyond the stdlib — reusable off-the-shelf across other repos.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import List, Tuple

_UA = "sai-agents-check/1.0 (+https://github.com/dnzengou/sai-agency)"
_TIMEOUT = 15


def _fetch(url: str) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — pinned base URL
        return resp.status, resp.read().decode("utf-8", errors="replace")


def check(base: str) -> Tuple[List[str], List[str]]:
    """Return (ok_messages, failures). Pure, no sys.exit — callable by tests."""
    base = base.rstrip("/")
    ok: List[str] = []
    fail: List[str] = []

    # 1) Dataset shape.
    try:
        status, body = _fetch(f"{base}/deals.json")
        data = json.loads(body)
        if status != 200 or not isinstance(data, dict) or not data.get("deals"):
            fail.append(f"/deals.json: unexpected shape (status={status})")
        elif data.get("schema_version") != 1:
            fail.append(f"/deals.json: schema_version={data.get('schema_version')} (expected 1)")
        else:
            ok.append(f"/deals.json: {len(data['deals'])} deals, schema v1")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        fail.append(f"/deals.json: {e!r}")

    # 2) llms.txt.
    try:
        status, body = _fetch(f"{base}/llms.txt")
        if status == 200 and body.lstrip().startswith("# "):
            ok.append("/llms.txt: present")
        else:
            fail.append(f"/llms.txt: status={status}, missing markdown heading")
    except Exception as e:
        fail.append(f"/llms.txt: {e!r}")

    # 3) /.well-known/agents.json.
    try:
        status, body = _fetch(f"{base}/.well-known/agents.json")
        manifest = json.loads(body)
        expected = {"dataset", "feed_rss", "sitemap", "home"}
        missing = expected - set(manifest.get("endpoints") or {})
        if status != 200 or missing:
            fail.append(f"/.well-known/agents.json: status={status}, missing endpoints={sorted(missing)}")
        else:
            ok.append("/.well-known/agents.json: capabilities=" + ",".join(manifest.get("capabilities") or []))
    except Exception as e:
        fail.append(f"/.well-known/agents.json: {e!r}")

    # 4) robots.txt names modern AI crawlers.
    try:
        status, body = _fetch(f"{base}/robots.txt")
        wanted = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "Google-Extended", "PerplexityBot")
        missing = [ua for ua in wanted if f"User-agent: {ua}" not in body]
        if status != 200 or missing:
            fail.append(f"/robots.txt: status={status}, missing crawlers={missing}")
        else:
            ok.append(f"/robots.txt: {len(wanted)} AI crawlers named")
    except Exception as e:
        fail.append(f"/robots.txt: {e!r}")

    # 5) sitemap lists agent entry points.
    try:
        status, body = _fetch(f"{base}/sitemap.xml")
        wanted = ("/llms.txt", "/.well-known/agents.json")
        missing = [u for u in wanted if u not in body]
        if status != 200 or missing:
            fail.append(f"/sitemap.xml: status={status}, missing={missing}")
        else:
            ok.append("/sitemap.xml: lists agent entry points")
    except Exception as e:
        fail.append(f"/sitemap.xml: {e!r}")

    return ok, fail


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "https://sai-agency-deals-radar.netlify.app"
    ok, fail = check(base)
    for line in ok:
        print(f"ok  · {line}")
    for line in fail:
        print(f"FAIL · {line}", file=sys.stderr)
    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()
