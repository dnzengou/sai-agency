from sai_agents.matching.scorer import MatchProfile, rank_matches, score_match

DEALS = [
    {"id": "h1", "title": "€1 house in Ollolai", "category": "repopulation", "region": "Southern Europe",
     "country": "Italy", "value_eur": 1, "sector": "Rural repopulation", "description": "abandoned home", "impact_score": 0.6},
    {"id": "b1", "title": "Bakery for sale", "category": "succession", "region": "Southern Europe",
     "country": "Spain", "value_eur": 150000, "sector": "Business succession", "description": "family bakery", "impact_score": 0.7},
    {"id": "v1", "title": "Rural venture fund", "category": "venture", "region": "EU",
     "country": "Germany", "value_eur": 15000000, "sector": "Search fund", "description": "SME acquisition", "impact_score": 0.5},
]


def test_category_and_country_match():
    p = MatchProfile(looking_for="home", countries=["Italy"])
    score, reasons = score_match(p, DEALS[0])
    assert score == 1.0  # both specified dims match
    assert any("category" in r for r in reasons)
    assert any("Italy" in r for r in reasons)


def test_partial_match_is_fractional():
    # wants a home in Spain; deal h1 is a home but in Italy -> category matches, country doesn't
    p = MatchProfile(looking_for="home", countries=["Spain"])
    score, _ = score_match(p, DEALS[0])
    # category weight 0.30 got, country weight 0.15 missed -> 0.30/0.45
    assert round(score, 2) == round(0.30 / 0.45, 2)


def test_budget_filtering():
    p = MatchProfile(looking_for="business", budget_min=50000, budget_max=200000)
    in_budget, _ = score_match(p, DEALS[1])   # 150k
    assert in_budget == 1.0
    p2 = MatchProfile(budget_min=1000000)
    out, _ = score_match(p2, DEALS[1])         # 150k < 1M -> budget missed
    assert out == 0.0


def test_unknown_price_partial_credit():
    d = dict(DEALS[1], value_eur=None)
    p = MatchProfile(budget_max=100000)
    score, reasons = score_match(p, d)
    assert 0 < score < 1
    assert any("price on request" in r for r in reasons)


def test_keyword_match():
    p = MatchProfile(keywords=["bakery"])
    score, reasons = score_match(p, DEALS[1])
    assert score == 1.0
    assert any("bakery" in r for r in reasons)


def test_empty_profile_matches_all():
    p = MatchProfile()
    assert score_match(p, DEALS[0])[0] == 1.0


def test_rank_orders_by_score_then_impact():
    p = MatchProfile(looking_for="business", countries=["Spain"])
    ranked = rank_matches(p, DEALS, top_n=3)
    assert ranked[0]["deal"]["id"] == "b1"     # perfect match first
    assert ranked[0]["score"] >= ranked[1]["score"]
    assert len(ranked) == 3
