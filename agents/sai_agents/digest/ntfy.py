"""ntfy push-digest publisher — lightweight, no-SMTP, mobile-first alternative
to the email digest.

ntfy.sh is a free HTTP pub/sub service (self-hostable). Users install the
ntfy iOS/Android app and subscribe to a topic; anyone who can POST to that
topic's URL delivers a notification to every subscriber. No accounts, no
SMTP, no mailing-list plumbing.

How this module uses it:
  * Deals from the public ``deals.json`` are grouped into a fixed, legible
    set of topics (``all``, ``high-impact``, per-category, per-region).
  * The publisher POSTs one message per non-empty topic — the top few deals
    in that slice, with a clickable link back to the filtered Deal Radar.
  * No secret state leaves this process: all data is already CC BY 4.0,
    topic names are deterministic from configuration.

Design mirrors ``DigestSender``:
  * Dry-run first (``SAI_NTFY_SERVER`` unset or ``dry_run=True``) writes a
    preview JSON instead of sending — nothing is silently lost.
  * HTTP transport is injectable, so tests never open a socket.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from sai_agents.logging_setup import get_logger

log = get_logger("digest.ntfy")

# Fixed topic taxonomy — human-legible, bounded, stable. Each slice is
# (slug, matcher) where matcher takes a deal dict and returns True/False.
# Keep this list small enough to be legible on the push-subscribe UI.
_HIGH_IMPACT_CUTOFF = 0.75

_DealMatcher = Callable[[Dict], bool]


def _by_category(cat: str) -> _DealMatcher:
    def match(d: Dict) -> bool:
        return (d.get("category") or "").lower() == cat
    return match


def _by_region(region: str) -> _DealMatcher:
    def match(d: Dict) -> bool:
        return (d.get("region") or "").lower() == region.lower()
    return match


def _high_impact(d: Dict) -> bool:
    return float(d.get("impact_score") or 0) >= _HIGH_IMPACT_CUTOFF


SLICES: List[Tuple[str, _DealMatcher, str]] = [
    # (slug, matcher, human-readable label)
    ("all", lambda d: True, "All new deals"),
    ("high-impact", _high_impact, "High-impact deals (≥ 0.75)"),
    # By category
    ("ai-ml", _by_category("ai_ml"), "AI / ML grants & funding"),
    ("succession", _by_category("succession"), "Family-business succession"),
    ("property", _by_category("repopulation"), "Property / relocation schemes"),
    ("venture", _by_category("venture"), "Venture vehicles"),
    # By region — the ones with enough flow to be worth a dedicated topic.
    ("nordics", _by_region("Nordics"), "Nordics"),
    ("southern-europe", _by_region("Southern Europe"), "Southern Europe"),
    ("uk-ireland", _by_region("UK & Ireland"), "UK & Ireland"),
    ("dach", _by_region("DACH"), "DACH (DE/AT/CH)"),
    ("benelux", _by_region("Benelux"), "Benelux (NL/BE/LU)"),
    ("latam", _by_region("LATAM"), "LATAM"),
    ("mena", _by_region("MENA"), "MENA"),
    ("east-africa", _by_region("East Africa"), "East Africa"),
    ("sub-saharan-africa", _by_region("Sub-Saharan Africa"), "Sub-Saharan Africa"),
    ("oceania", _by_region("Oceania"), "Oceania"),
    ("south-asia", _by_region("South Asia"), "South Asia"),
    ("southeast-asia", _by_region("Southeast Asia"), "Southeast Asia"),
    ("east-asia", _by_region("East Asia"), "East Asia"),
    ("canada", _by_region("Canada"), "Canada"),
]


@dataclass
class NtfyConfig:
    server: str = "https://ntfy.sh"
    topic_prefix: str = "sai-deals-v1"
    token: str = ""  # optional bearer for self-hosted / ntfy.sh Pro
    site_url: str = "https://sai-agency-deals-radar.netlify.app"
    max_per_topic: int = 5
    high_impact_priority: int = 4  # ntfy 1-5; default is 3

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "NtfyConfig":
        env = env if env is not None else dict(os.environ)
        return cls(
            server=env.get("SAI_NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            topic_prefix=env.get("SAI_NTFY_TOPIC_PREFIX", "sai-deals-v1"),
            token=env.get("SAI_NTFY_TOKEN", ""),
            site_url=env.get("SAI_SITE_URL", "https://sai-agency-deals-radar.netlify.app").rstrip("/"),
            max_per_topic=int(env.get("SAI_NTFY_MAX_PER_TOPIC", "5")),
        )

    @property
    def enabled(self) -> bool:
        # Explicitly opt-in via the server env var being set — the default
        # https://ntfy.sh is a real public endpoint, so we treat the *absence*
        # of a project-specific choice as "stay in dry-run".
        return bool(os.environ.get("SAI_NTFY_SERVER"))


def _topic_name(cfg: NtfyConfig, slug: str) -> str:
    return f"{cfg.topic_prefix}-{slug}"


def group_deals_by_topic(dataset: Dict, cfg: NtfyConfig) -> Dict[str, List[Dict]]:
    """Return ``{slug: [top-N deals in that slice]}``.

    Deals are sorted by ``arm_priority`` then ``impact_score`` within each
    slice — the same order a buyer-side agent would use — and capped at
    ``cfg.max_per_topic`` so each notification stays scannable on a phone.
    Only open/upcoming deals are pushed (announced/closed are backlog).
    """
    open_deals = [d for d in dataset.get("deals", []) if d.get("stage") in ("open", "upcoming")]

    def sort_key(d: Dict) -> float:
        return float(d.get("arm_priority") or d.get("impact_score") or 0)

    out: Dict[str, List[Dict]] = {}
    for slug, matcher, _label in SLICES:
        matched = sorted([d for d in open_deals if matcher(d)], key=sort_key, reverse=True)
        if matched:
            out[slug] = matched[: cfg.max_per_topic]
    return out


def _build_payload(slug: str, label: str, deals: List[Dict], cfg: NtfyConfig) -> Dict:
    """Shape one ntfy POST payload (title + body + click + priority + tags)."""
    titles = [d.get("title", "")[:70] for d in deals]
    lines = []
    for d in deals:
        meta = " · ".join(filter(None, [
            d.get("country", ""),
            d.get("type", "").replace("_", " "),
            (f"deadline {d['deadline']}" if d.get("deadline") else ""),
        ]))
        lines.append(f"• {d.get('title','')[:80]} — {meta}")
    body = "\n".join(lines)

    # Link back to the filtered Deal Radar so a tap opens the right view.
    # The site already honours ?region= / ?category= URL filters (see assets/deals.js).
    click_params = {
        "ai-ml": "category=ai_ml",
        "succession": "category=succession",
        "property": "category=repopulation",
        "venture": "category=venture",
    }
    if slug in click_params:
        click = f"{cfg.site_url}/deals?{click_params[slug]}"
    elif slug in {s[0] for s in SLICES if s[0] not in ("all", "high-impact")}:
        # region slice — match the UI's region chip name case-insensitively.
        region = next((s[2] for s in SLICES if s[0] == slug), slug)
        click = f"{cfg.site_url}/deals?region={urllib_quote(region)}"
    else:
        click = f"{cfg.site_url}/deals"

    priority = cfg.high_impact_priority if slug == "high-impact" else 3
    # Emoji tags ntfy renders in the notification; keep white-hat / informative.
    tag_map = {
        "ai-ml": "robot",
        "succession": "family",
        "property": "house",
        "venture": "rocket",
        "high-impact": "star",
    }
    tags = [tag_map.get(slug, "earth_africa"), "sai-deal-radar"]

    return {
        "topic": _topic_name(cfg, slug),
        "title": f"{len(deals)} new {label}",
        "message": body,
        "priority": priority,
        "tags": tags,
        "click": click,
        "actions": [
            {"action": "view", "label": "Open Deal Radar", "url": click, "clear": True},
        ],
    }


def urllib_quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s)


class NtfyPublisher:
    """POSTs one message per non-empty slice. Transport is injectable."""

    def __init__(
        self,
        config: Optional[NtfyConfig] = None,
        post_fn: Optional[Callable[[str, bytes, Dict[str, str]], Tuple[int, str]]] = None,
        preview_path: Optional[str] = None,
    ) -> None:
        self.config = config or NtfyConfig.from_env()
        self._post = post_fn or _default_post
        self.preview_path = preview_path

    def publish(self, dataset: Dict, dry_run: bool = False) -> Dict:
        """Publish the digest. Returns ``{topics, sent, dry_run, failed, payloads}``."""
        cfg = self.config
        by_topic = group_deals_by_topic(dataset, cfg)
        payloads: List[Dict] = [
            _build_payload(slug, label, by_topic[slug], cfg)
            for slug, _m, label in SLICES
            if slug in by_topic
        ]
        result = {
            "topics": len(payloads),
            "sent": 0,
            "dry_run": 0,
            "failed": 0,
            "payloads": payloads,
        }

        if dry_run or not cfg.enabled:
            if self.preview_path:
                Path(self.preview_path).write_text(
                    json.dumps(payloads, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            log.warning(
                "digest.ntfy.dry_run",
                reason=("explicit" if dry_run else "SAI_NTFY_SERVER not set"),
                topics=len(payloads),
                preview=self.preview_path,
            )
            result["dry_run"] = len(payloads)
            return result

        for p in payloads:
            url = f"{cfg.server}/{p['topic']}"
            # ntfy accepts either a JSON POST (newer) or title/priority/tags
            # as headers. JSON is cleaner and tests inspect it directly.
            # Strip the topic from the payload before sending because the URL
            # already names it; ntfy's JSON variant uses a top-level `topic`
            # field, but the simpler path is header + body.
            body = p["message"].encode("utf-8")
            headers = {
                "Title": p["title"],
                "Priority": str(p["priority"]),
                "Tags": ",".join(p["tags"]),
                "Click": p["click"],
                "Content-Type": "text/plain; charset=utf-8",
            }
            if cfg.token:
                headers["Authorization"] = f"Bearer {cfg.token}"
            try:
                status, _text = self._post(url, body, headers)
                if 200 <= status < 300:
                    result["sent"] += 1
                else:
                    result["failed"] += 1
                    log.error("digest.ntfy.http", topic=p["topic"], status=status)
            except Exception as exc:  # one bad topic must not stop the rest
                result["failed"] += 1
                log.error("digest.ntfy.send_failed", topic=p["topic"], error=str(exc))
        log.info(
            "digest.ntfy.done",
            topics=result["topics"],
            sent=result["sent"],
            failed=result["failed"],
        )
        return result


def _default_post(url: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.reason or ""


# --------------------------------------------------------------------------- #
# Topic discovery helpers — consumed by the subscribe UI on the Deal Radar.
# --------------------------------------------------------------------------- #
def topic_catalog(cfg: Optional[NtfyConfig] = None) -> List[Dict[str, str]]:
    """Return ``[{slug, topic, label, subscribe_url, deep_link}]`` for every
    slice — the UI iterates this to render subscribe buttons."""
    cfg = cfg or NtfyConfig.from_env()
    out = []
    for slug, _m, label in SLICES:
        topic = _topic_name(cfg, slug)
        out.append({
            "slug": slug,
            "topic": topic,
            "label": label,
            # Web URL — opens the ntfy webapp or the installed PWA.
            "subscribe_url": f"{cfg.server}/{topic}",
            # Deep-link that opens the ntfy iOS/Android app directly.
            "deep_link": f"ntfy://subscribe/{topic}",
        })
    return out
