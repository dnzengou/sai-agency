from sai_agents.deals.deal_sourcing_agent import DealSourcingAgent
from sai_agents.models import Deal, DealType


def _deal(title, impact, stage, country="Spain", region="Southern Europe", sector="AI/ML", dtype="grant"):
    d = Deal(
        title=title, org="Org", type=DealType(dtype),
        country=country, region=region, sector=sector, stage=stage,
    )
    d.impact_score = impact
    return d


def test_skill_match_fraction():
    d = _deal("x", 0.5, "open", country="Kenya", region="East Africa", sector="AgTech", dtype="grant")
    loadout = {"east africa", "grant", "unused"}
    # 2 of the deal's 4 attrs (region, type) are in a 3-skill loadout => 2/3.
    assert abs(DealSourcingAgent._skill_match(d, loadout) - 2 / 3) < 1e-9
    assert DealSourcingAgent._skill_match(d, set()) == 0.0


def test_loadout_boost_promotes_matching_deal():
    # Two open deals of equal-ish impact; the loadout matches only the second.
    agent = DealSourcingAgent(spec={"exploration": 0.9, "recency_weight": 0.2}, loadout=["latam", "accelerator"])
    plain = _deal("plain", 0.60, "open", country="Spain", region="Southern Europe", sector="AI/ML", dtype="grant")
    matched = _deal("matched", 0.55, "open", country="Chile", region="LATAM", sector="Venture", dtype="accelerator")
    ranked = agent._arm_rank([plain, matched])
    assert ranked[0].title == "matched"  # skill match overcomes the small impact gap


def test_loadout_boost_gated_by_exploration():
    # Same deals, but exploration ~0 => the loadout bonus is switched off, so
    # the higher-impact non-matching deal stays on top.
    agent = DealSourcingAgent(spec={"exploration": 0.0, "recency_weight": 0.0}, loadout=["latam", "accelerator"])
    plain = _deal("plain", 0.60, "open", country="Spain", region="Southern Europe", sector="AI/ML", dtype="grant")
    matched = _deal("matched", 0.55, "open", country="Chile", region="LATAM", sector="Venture", dtype="accelerator")
    ranked = agent._arm_rank([plain, matched])
    assert ranked[0].title == "plain"


def test_loadout_only_still_reranks_without_spec():
    # Loadout present but no champion spec (spec None => neutral 0.5 knobs).
    agent = DealSourcingAgent(loadout=["latam"])
    agent.spec = None
    plain = _deal("plain", 0.62, "open", region="Southern Europe")
    matched = _deal("matched", 0.60, "open", region="LATAM")
    ranked = agent._arm_rank([plain, matched])
    # Guard no longer short-circuits when a loadout exists; match nudges order.
    assert {d.title for d in ranked} == {"plain", "matched"}
    assert ranked[0].title == "matched"


def test_run_records_loadout_match_in_payload():
    agent = DealSourcingAgent(spec={"exploration": 0.9}, loadout=["southern europe"])
    result = agent.execute({"top_n": 3})
    assert "loadout" in result.payload and result.payload["loadout"] == ["southern europe"]
    assert result.payload["loadout_matched"] >= 0
