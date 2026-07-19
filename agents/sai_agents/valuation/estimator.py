"""Deterministic, transparent valuation estimates.

Produces an indicative EUR range for an opportunity with an explicit ``basis``
and ``confidence`` so the number is never mistaken for an appraisal:

  * disclosed figures are used directly (highest confidence);
  * €1/€3 house schemes are shown as symbolic acquisition + a typical
    renovation budget (medium confidence);
  * where nothing is disclosed, a clearly-labelled sector-typical band is used
    (low confidence);
  * grants/incentives are framed as a benefit ("up to"), not a cost.

Pure and side-effect free; mirrored for display in the frontend by reading the
embedded ``valuation`` object (no logic duplicated client-side).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Typical renovation budget for an abandoned village home (EUR).
_RENO_LOW, _RENO_HIGH = 20_000, 70_000

# Sector-typical transfer bands for a small business when no price is disclosed.
_SECTOR_BANDS = {
    "agriculture": (100_000, 800_000),
    "farm": (100_000, 800_000),
    "retail": (30_000, 250_000),
    "shop": (30_000, 250_000),
    "hospitality": (80_000, 600_000),
    "healthtech": (150_000, 1_500_000),
}
_SUCCESSION_DEFAULT = (50_000, 500_000)


def _sector_band(sector: str) -> tuple[int, int]:
    s = (sector or "").lower()
    for key, band in _SECTOR_BANDS.items():
        if key in s:
            return band
    return _SUCCESSION_DEFAULT


def _get(deal: Any, key: str, default=None):
    if isinstance(deal, dict):
        return deal.get(key, default)
    return getattr(deal, key, default)


def estimate_value(deal: Any) -> Dict[str, Any]:
    """Return an indicative valuation dict for a deal (dict or model)."""
    dtype = str(_get(deal, "type", "") or "")
    if hasattr(dtype, "value"):  # enum passthrough
        dtype = dtype.value  # pragma: no cover
    dtype = dtype.split(".")[-1].lower()
    sector = str(_get(deal, "sector", "") or "")
    value = _get(deal, "value_eur")
    try:
        value = float(value) if value is not None else None
    except (TypeError, ValueError):
        value = None

    # --- €1 / relocation schemes: symbolic acquisition + renovation budget ---
    if dtype == "property_scheme":
        acq = value if (value is not None and value > 0) else 1.0
        return _mk(acq + _RENO_LOW, acq + _RENO_HIGH,
                   basis="symbolic acquisition + typical renovation",
                   confidence="medium", disclosed=value is not None,
                   note="Acquisition is symbolic; the real cost is renovation.")

    # --- Grants / incentives / accelerators: a benefit, framed "up to" ---
    if dtype in ("grant", "accelerator"):
        if value and value > 0:
            return _mk(None, value, basis="grant / benefit (up to disclosed)",
                       confidence="high", disclosed=True, kind="benefit",
                       note="Support available, not a purchase price.")
        return _mk(None, None, basis="benefit — varies (see source)",
                   confidence="low", disclosed=False, kind="benefit")

    # --- Disclosed monetary figure (rounds, tenders, big schemes) ---
    if value is not None and value > 0:
        if dtype in ("funding_round", "public_tender", "rfp", "partnership"):
            return _mk(value, value, basis="disclosed figure",
                       confidence="high", disclosed=True)
        # business_succession / venture with a disclosed number -> ±30% band
        return _mk(value * 0.7, value * 1.3, basis="disclosed (indicative ±30%)",
                   confidence="medium", disclosed=True)

    # --- No disclosed figure ---
    if dtype == "business_succession":
        lo, hi = _sector_band(sector)
        return _mk(lo, hi, basis="sector-typical transfer band (indicative)",
                   confidence="low", disclosed=False)
    if dtype == "venture":
        return _mk(None, None, basis="ticket / fund size — varies",
                   confidence="low", disclosed=False, kind="investment")

    return _mk(None, None, basis="varies — see source", confidence="low", disclosed=False)


def _mk(low, high, basis, confidence, disclosed, kind="cost", note="") -> Dict[str, Any]:
    return {
        "low_eur": round(low, 2) if isinstance(low, (int, float)) else None,
        "high_eur": round(high, 2) if isinstance(high, (int, float)) else None,
        "currency": "EUR",
        "basis": basis,
        "confidence": confidence,
        "disclosed": bool(disclosed),
        "kind": kind,  # cost | benefit | investment
        "note": note,
    }


def _eur(n: float) -> str:
    if n >= 1e9:
        return f"€{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"€{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"€{round(n / 1e3)}k"
    return f"€{n:.0f}"


def format_estimate(v: Optional[Dict[str, Any]]) -> str:
    """Short human string, e.g. '€20k–€70k · indicative'."""
    if not v:
        return "—"
    lo, hi = v.get("low_eur"), v.get("high_eur")
    prefix = "up to " if v.get("kind") == "benefit" else ""
    if lo is None and hi is None:
        return v.get("basis", "varies")  # no figure to qualify with a tag
    if lo is None:
        rng = f"{prefix}{_eur(hi)}"
    elif hi is None:
        rng = f"from {_eur(lo)}"
    elif lo == hi:
        rng = _eur(lo)
    else:
        rng = f"{_eur(lo)}–{_eur(hi)}"
    tag = "disclosed" if v.get("disclosed") and v.get("confidence") == "high" else "indicative"
    return f"{rng} · {tag}"
