"""Deterministic match scoring.

A ``MatchProfile`` captures what a user wants (what to take over, where, budget,
sector interests). ``score_match`` compares it to a deal and returns a 0..1
score plus human-readable reasons. **Only the dimensions the user actually
specified count** toward the score, so the percentage reflects fit against
their stated preferences rather than being diluted by blanks.

Kept intentionally simple and pure (no LLM) so it is testable and can be
mirrored 1:1 in JavaScript for the static site.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# Weights per dimension (used only when the user specified that dimension).
_W = {
    "category": 0.30,
    "region": 0.15,
    "country": 0.15,
    "budget": 0.20,
    "sector": 0.20,
}

# "What are you looking for?" -> deal category.
LOOKING_FOR_CATEGORY = {
    "home": "repopulation",
    "business": "succession",
    "invest": "venture",
    "ai": "ai_ml",
}


class MatchProfile(BaseModel):
    looking_for: Optional[str] = None      # home | business | invest | ai (or a category)
    regions: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    keywords: List[str] = Field(default_factory=list)  # sector / free-text interests

    def target_category(self) -> Optional[str]:
        if not self.looking_for:
            return None
        lf = self.looking_for.strip().lower()
        return LOOKING_FOR_CATEGORY.get(lf, lf)


def _budget_ok(deal: Dict, lo: Optional[float], hi: Optional[float]) -> Optional[bool]:
    v = deal.get("value_eur")
    if v is None:
        return None  # unknown — neutral, neither matched nor rejected
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def score_match(profile: MatchProfile, deal: Dict) -> Tuple[float, List[str]]:
    total_w = 0.0
    got_w = 0.0
    reasons: List[str] = []

    cat = profile.target_category()
    if cat:
        total_w += _W["category"]
        if deal.get("category") == cat:
            got_w += _W["category"]
            reasons.append(f"category: {cat}")

    if profile.regions:
        total_w += _W["region"]
        if deal.get("region") in profile.regions:
            got_w += _W["region"]
            reasons.append(f"region: {deal.get('region')}")

    if profile.countries:
        total_w += _W["country"]
        if deal.get("country") in profile.countries:
            got_w += _W["country"]
            reasons.append(f"country: {deal.get('country')}")

    if profile.budget_min is not None or profile.budget_max is not None:
        total_w += _W["budget"]
        ok = _budget_ok(deal, profile.budget_min, profile.budget_max)
        if ok is True:
            got_w += _W["budget"]
            reasons.append("within budget")
        elif ok is None:
            got_w += _W["budget"] * 0.4  # unknown price — partial credit
            reasons.append("price on request")

    if profile.keywords:
        total_w += _W["sector"]
        hay = " ".join(str(deal.get(k, "")) for k in ("title", "sector", "description", "org")).lower()
        hit = next((kw for kw in profile.keywords if kw.strip() and kw.strip().lower() in hay), None)
        if hit:
            got_w += _W["sector"]
            reasons.append(f"matches '{hit}'")

    # No preferences given -> everyone is a match; rank by impact downstream.
    score = 1.0 if total_w == 0 else round(got_w / total_w, 4)
    return score, reasons


def rank_matches(profile: MatchProfile, deals: List[Dict], top_n: int = 12) -> List[Dict]:
    scored = []
    for d in deals:
        score, reasons = score_match(profile, d)
        scored.append({"deal": d, "score": score, "reasons": reasons})
    scored.sort(key=lambda m: (m["score"], m["deal"].get("impact_score") or 0), reverse=True)
    return scored[:top_n]
