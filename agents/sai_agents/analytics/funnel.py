"""Funnel analytics — turn the NDJSON lead store into conversion metrics.

The funnel the business cares about:

    subscribers (deal-alerts)  ->  interests (deal-interest, a hand-raise on a
    specific deal)  ->  engaged (ARM stage)  ->  won

Plus breakdowns (by form / ARM stage / owner / region), the top deals by
interest, and impact stats. Pure and deterministic; reads a list of lead dicts.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


def load_leads(path: Optional[str]) -> List[Dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    leads: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            leads.append(json.loads(line))
        except Exception:
            continue
    return leads


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def compute_funnel(leads: List[Dict]) -> Dict:
    total = len(leads)
    by_form = Counter(l.get("form", "unknown") for l in leads)
    by_arm = Counter(l.get("arm_stage", "unknown") for l in leads)
    by_owner = Counter(l.get("owner", "unassigned") for l in leads)
    by_region = Counter((l.get("region") or "unknown") for l in leads if l.get("form") == "deal-interest")

    subscribers = by_form.get("deal-alerts", 0)
    interests = by_form.get("deal-interest", 0)
    engaged = by_arm.get("engaged", 0)
    won = by_arm.get("won", 0)

    # Top deals by interest volume (deal-interest leads name a deal).
    deal_counts = Counter(
        (l.get("deal") or "").strip()
        for l in leads
        if l.get("form") == "deal-interest" and l.get("deal")
    )
    top_deals = [{"deal": d, "interest": c} for d, c in deal_counts.most_common(10)]

    impacts = [l["impact_score"] for l in leads if isinstance(l.get("impact_score"), (int, float))]
    avg_impact = round(sum(impacts) / len(impacts), 4) if impacts else 0.0

    return {
        "total_leads": total,
        "funnel": {
            "subscribers": subscribers,
            "interests": interests,
            "engaged": engaged,
            "won": won,
        },
        "conversion": {
            # Of everyone who engaged with a form, how many raised a hand on a deal.
            "interest_rate": _ratio(interests, subscribers + interests),
            # Of deal-interest leads, how many reached the engaged ARM stage.
            "engaged_rate": _ratio(engaged, interests),
            "won_rate": _ratio(won, interests),
        },
        "by_form": dict(by_form),
        "by_arm_stage": dict(by_arm),
        "by_owner": dict(by_owner),
        "interest_by_region": dict(by_region),
        "top_deals_by_interest": top_deals,
        "avg_impact_score": avg_impact,
    }
