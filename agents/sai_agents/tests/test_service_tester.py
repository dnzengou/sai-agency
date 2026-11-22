from sai_agents.config import Settings
from sai_agents.models import HealthResult
from sai_agents.service_testers.service_tester_agent import ServiceTesterAgent


def _agent(probe):
    settings = Settings(kafka_enabled=False, target_url="https://example.test")
    agent = ServiceTesterAgent(settings)
    agent._probe = probe
    return agent


def test_healthy_probe_yields_fitness_and_availability():
    def probe(url, timeout):
        return HealthResult(url=url, ok=True, status_code=200, latency_ms=120.0)

    result = _agent(probe).execute({})
    assert result.ok
    assert result.fitness is not None
    assert result.fitness.score > 0.9
    assert result.fitness.components["availability"] == 1.0
    assert any("reachable" in i.title.lower() for i in result.insights)


def test_slow_site_flags_performance():
    def probe(url, timeout):
        return HealthResult(url=url, ok=True, status_code=200, latency_ms=2200.0)

    result = _agent(probe).execute({})
    assert any("slow" in i.title.lower() for i in result.insights)
    assert any("cach" in r.action.lower() for r in result.recommendations)


def test_down_site_is_critical():
    def probe(url, timeout):
        return HealthResult(url=url, ok=False, status_code=503, latency_ms=None, error="503")

    result = _agent(probe).execute({})
    assert not result.ok
    assert result.fitness.score < 0.4
    assert any(i.severity.value == "critical" for i in result.insights)


async def test_run_and_publish_emits_event():
    def probe(url, timeout):
        return HealthResult(url=url, ok=True, status_code=200, latency_ms=100.0)

    from sai_agents.kafca.publisher import KafkaEventPublisher

    settings = Settings(kafka_enabled=False)
    agent = ServiceTesterAgent(settings)
    agent._probe = probe
    pub = KafkaEventPublisher(settings)
    async with pub:
        await agent.run_and_publish(publisher=pub)
    assert len(pub.event_log) == 1
    assert pub.event_log[0].fitness is not None
