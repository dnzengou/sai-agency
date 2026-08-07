"""EvoForge/EvoSkillOpt feedback into agent behaviour."""

from sai_agents.agents.marketing_agent import MarketingAgent
from sai_agents.config import Settings
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.models import HealthResult
from sai_agents.orchestrator import OrchestratorTeam
from sai_agents.service_testers.service_tester_agent import ServiceTesterAgent


def test_neutral_spec_is_a_noop():
    baseline = MarketingAgent().execute({"target_url": "https://x.test"})
    neutral = MarketingAgent(
        spec={"exploration": 0.5, "impact_bias": 0.5, "risk_tolerance": 0.5, "recency_weight": 0.5},
        loadout=["seo"],
    ).execute({"target_url": "https://x.test"})
    # Exploration at/below the 0.6 gate => identical recommendation count.
    assert len(neutral.recommendations) == len(baseline.recommendations)


def test_high_exploration_broadens_with_top_skill():
    agent = MarketingAgent(spec={"exploration": 0.9}, loadout=["pentest", "seo"])
    result = agent.execute({"target_url": "https://x.test"})
    actions = [r.action for r in result.recommendations]
    assert any("pentest" in a and "Exploratory" in a for a in actions)
    # Impact scores are never rescaled by the spec — still bounded and sane.
    assert 0.0 <= result.aggregate_impact <= 1.0


def test_high_exploration_without_loadout_does_nothing():
    agent = MarketingAgent(spec={"exploration": 0.95}, loadout=[])
    result = agent.execute({"target_url": "https://x.test"})
    assert not any("Exploratory" in r.action for r in result.recommendations)


def test_event_records_spec_provenance():
    agent = MarketingAgent(spec={"exploration": 0.3}, loadout=["seo", "content"])
    result = agent.execute({"target_url": "https://x.test"})
    event = agent.to_event(result)
    assert event.payload.get("genome_spec") == agent.spec
    assert event.payload.get("loadout") == ["seo", "content"]


def test_unevolved_agent_has_no_provenance_key():
    agent = MarketingAgent()  # no spec
    event = agent.to_event(agent.execute({}))
    assert "genome_spec" not in event.payload


async def test_orchestrator_injects_specs_and_reports_them():
    settings = Settings(kafka_enabled=False, target_url="https://example.test")
    pub = KafkaEventPublisher(settings)
    tester = ServiceTesterAgent(settings)
    tester._probe = lambda url, timeout: HealthResult(url=url, ok=True, status_code=200, latency_ms=90.0)

    team = OrchestratorTeam(
        settings,
        publisher=pub,
        evolved_specs={"marketing": {"exploration": 0.9}},
        skill_loadout=["seo", "content"],
    )
    team.tester = tester
    # Marketing agent received the injected spec + loadout.
    assert team.marketing.spec == {"exploration": 0.9}
    assert team.marketing.loadout == ["seo", "content"]

    summary = await team.run({"headers": {}})
    assert summary["events_published"] == 7  # unchanged: injection is additive
    marketing = next(r for r in summary["results"] if r["agent"] == "marketing")
    assert any("Exploratory: double down on 'seo'" in r["action"] for r in marketing["recommendations"])
