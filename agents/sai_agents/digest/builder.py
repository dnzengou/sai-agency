"""Compose the digest email (HTML + plain text) from the deal dataset."""

from __future__ import annotations

import html
from typing import Dict, List, Optional, Tuple

from sai_agents.deals.site import DEFAULT_SITE, deal_url, euro

_TYPE_LABEL = {
    "grant": "Grant",
    "public_tender": "Public tender",
    "accelerator": "Accelerator",
    "funding_round": "Funding round",
    "partnership": "Partnership",
    "rfp": "RFP",
}
_OPEN = {"open", "upcoming"}


def select_deals(dataset: Dict, region: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Pick the most relevant deals: open/upcoming first, then by impact."""
    deals = dataset.get("deals", [])
    if region and region != "All":
        deals = [d for d in deals if d.get("region") == region]

    def key(d: Dict):
        return (0 if d.get("stage") in _OPEN else 1, -(d.get("impact_score") or 0))

    return sorted(deals, key=key)[:limit]


def _esc(v: object) -> str:
    return html.escape("" if v is None else str(v))


def build_digest(
    dataset: Dict,
    region: Optional[str] = None,
    limit: int = 10,
    site_url: str = DEFAULT_SITE,
    subject_prefix: str = "SAI Agency Deal Radar",
) -> Tuple[str, str, str]:
    """Return (subject, html_body, text_body)."""
    deals = select_deals(dataset, region, limit)
    scope = region if (region and region != "All") else "Southern Europe, the Nordics & EU"
    subject = f"{subject_prefix} — {len(deals)} AI/ML opportunities ({scope})"

    # --- HTML ---
    rows = []
    for d in deals:
        url = deal_url(d, site_url)
        badge = _TYPE_LABEL.get(d.get("type", ""), d.get("type", ""))
        meta = " · ".join(filter(None, [
            badge,
            " ".join(filter(None, [d.get("org"), d.get("country") and f"({d['country']})"])),
            euro(d.get("value_eur")) if d.get("value_eur") else "",
            f"deadline {d['deadline']}" if d.get("deadline") else "",
        ]))
        rows.append(
            f'<tr><td style="padding:14px 0;border-bottom:1px solid #e1e0d9;">'
            f'<a href="{_esc(url)}" style="color:#2a78d6;text-decoration:none;font-weight:600;font-size:15px;">{_esc(d.get("title",""))}</a>'
            f'<div style="color:#52514e;font-size:13px;margin:3px 0 6px;">{_esc(meta)}</div>'
            f'<div style="color:#333;font-size:13px;">{_esc((d.get("description") or "")[:180])}</div>'
            f'<a href="{_esc(url)}" style="color:#2a78d6;font-size:13px;">View &amp; pursue →</a>'
            f"</td></tr>"
        )
    html_body = (
        f'<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:640px;margin:0 auto;color:#0b0b0b;">'
        f'<h1 style="font-size:20px;margin:0 0 4px;">SAI Agency · Deal Radar</h1>'
        f'<p style="color:#52514e;font-size:14px;margin:0 0 16px;">This week\'s AI/ML/data opportunities across {_esc(scope)}.</p>'
        f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'
        f'<p style="margin:22px 0 0;"><a href="{_esc(site_url)}/deals" style="background:#2a78d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">See all deals →</a></p>'
        f'<p style="color:#898781;font-size:12px;margin:22px 0 0;">You subscribed to deal alerts at {_esc(site_url)}/deals. '
        f'Reply "unsubscribe" to stop. Verify details at the source before acting.</p>'
        f"</div>"
    )

    # --- Plain text ---
    lines = [f"SAI Agency · Deal Radar — this week ({scope})", ""]
    for d in deals:
        lines.append(f"- {d.get('title','')}")
        m = " · ".join(filter(None, [_TYPE_LABEL.get(d.get('type',''), ''), d.get('org',''), d.get('country','')]))
        if m:
            lines.append(f"  {m}")
        lines.append(f"  {deal_url(d, site_url)}")
    lines += ["", f"See all: {site_url}/deals", "Unsubscribe: reply 'unsubscribe'."]
    text_body = "\n".join(lines)

    return subject, html_body, text_body
