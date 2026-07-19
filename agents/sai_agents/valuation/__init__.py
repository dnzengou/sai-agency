"""Valuation — indicative money-scale estimates for sourced opportunities.

Executes the business plan's "Valuation Agent" in a deliberately conservative,
transparent way: a deterministic estimate with an explicit basis and confidence,
never fabricated precision. Computed once at generate-time and embedded in
``deals.json`` so every surface (detail pages, matches, cards) reads the same
number.
"""

from sai_agents.valuation.estimator import estimate_value, format_estimate

__all__ = ["estimate_value", "format_estimate"]
