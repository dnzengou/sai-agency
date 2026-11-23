from sai_agents.config import Settings
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.valuation.estimator import estimate_value, format_estimate


def test_property_scheme_symbolic_plus_reno():
    v = estimate_value({"type": "property_scheme", "value_eur": 1})
    assert v["low_eur"] == 20001 and v["high_eur"] == 70001
    assert v["kind"] == "cost" and v["confidence"] == "medium"
    assert "renovation" in v["basis"]


def test_grant_with_value_is_benefit_up_to():
    v = estimate_value({"type": "grant", "value_eur": 30000})
    assert v["kind"] == "benefit" and v["high_eur"] == 30000 and v["low_eur"] is None
    assert format_estimate(v).startswith("up to €30k")


def test_grant_without_value_varies():
    v = estimate_value({"type": "grant", "value_eur": None})
    assert v["low_eur"] is None and v["high_eur"] is None
    assert format_estimate(v) == v["basis"]


def test_funding_round_disclosed_exact():
    v = estimate_value({"type": "funding_round", "value_eur": 15_000_000})
    assert v["low_eur"] == v["high_eur"] == 15_000_000
    assert v["disclosed"] and v["confidence"] == "high"
    assert format_estimate(v) == "€15.0M · disclosed"


def test_business_succession_sector_band():
    farm = estimate_value({"type": "business_succession", "value_eur": None, "sector": "Agriculture"})
    assert farm["low_eur"] == 100_000 and farm["high_eur"] == 800_000
    generic = estimate_value({"type": "business_succession", "value_eur": None, "sector": "Misc"})
    assert generic["low_eur"] == 50_000 and generic["high_eur"] == 500_000
    assert farm["confidence"] == "low"


def test_business_succession_with_value_band():
    v = estimate_value({"type": "business_succession", "value_eur": 200_000})
    assert v["low_eur"] == 140_000 and v["high_eur"] == 260_000


def test_venture_varies():
    v = estimate_value({"type": "venture", "value_eur": None})
    assert v["kind"] == "investment" and v["low_eur"] is None


def test_format_none():
    assert format_estimate(None) == "—"


def test_pipeline_embeds_valuation():
    deals = KafCadePipeline(settings=Settings(kafka_enabled=False)).collect()
    assert deals, "expected bundled deals"
    assert all(d.valuation is not None for d in deals)
    # a €1 house should carry a renovation-based estimate
    houses = [d for d in deals if d.type.value == "property_scheme"]
    assert houses and houses[0].valuation["low_eur"] >= 20000
