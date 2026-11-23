"""Matchmaking — score sourced opportunities against a buyer/successor profile.

Executes the business plan's "Matchmaking Agent": turn a would-be successor,
buyer or investor's preferences into a ranked, explained shortlist of real
opportunities. ARM-aligned and deterministic; mirrored client-side in
``assets/match.js`` so it runs on the static site over ``deals.json``.
"""

from sai_agents.matching.scorer import MatchProfile, rank_matches, score_match

__all__ = ["MatchProfile", "score_match", "rank_matches"]
