import json
import urllib.request

from sai_agents.config import Settings
from sai_agents.ingest.crm import CRMSink, event_to_lead
from sai_agents.ingest.server import LeadIngestServer
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.models import EventType, EvolutionEvent


def _lead_event():
    return EvolutionEvent(
        event_type=EventType.LEAD_SIGNAL,
        source_agent="lead_bridge",
        impact_score=0.76,
        payload={
            "form": "deal-interest",
            "arm_stage": "engaged",
            "owner": "sales_gtm",
            "priority": "high",
            "next_action": "Qualify within 24h",
            "lead": {"name": "Jane", "email": "jane@acme.eu", "company": "Acme", "deal": "Verda round"},
        },
    )


def test_event_to_lead_flattens():
    lead = event_to_lead(_lead_event())
    assert lead["email"] == "jane@acme.eu"
    assert lead["company"] == "Acme"
    assert lead["arm_stage"] == "engaged"
    assert lead["impact_score"] == 0.76
    assert lead["form"] == "deal-interest"


def test_ndjson_store_appends(tmp_path):
    store = tmp_path / "leads.ndjson"
    sink = CRMSink(store_path=str(store))
    assert sink.enabled
    r1 = sink.record(_lead_event())
    r2 = sink.record(_lead_event())
    assert r1["stored"] and r2["stored"]
    assert r1["forwarded"] is False  # no webhook configured
    lines = store.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["email"] == "jane@acme.eu"


def test_webhook_forward_uses_poster_and_token():
    captured = {}

    def poster(url, body, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        return 200

    sink = CRMSink(webhook_url="https://crm.example/hook", webhook_token="tok", poster=poster)
    result = sink.record(_lead_event())
    assert result["forwarded"] is True
    assert captured["url"] == "https://crm.example/hook"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["body"]["email"] == "jane@acme.eu"


def test_webhook_failure_is_contained():
    def poster(url, body, headers, timeout):
        return 500

    sink = CRMSink(webhook_url="https://crm.example/hook", poster=poster)
    assert sink.record(_lead_event())["forwarded"] is False


def test_disabled_sink_is_noop():
    sink = CRMSink()
    assert sink.enabled is False
    assert sink.record(_lead_event()) == {"stored": False, "forwarded": False}


def test_ingest_records_lead_to_crm(tmp_path):
    store = tmp_path / "leads.ndjson"
    forwarded = []
    crm = CRMSink(store_path=str(store), webhook_url="https://crm/x",
                  poster=lambda *a: (forwarded.append(a) or 200))
    pub = KafkaEventPublisher(Settings(kafka_enabled=False))
    srv = LeadIngestServer(Settings(kafka_enabled=False), publisher=pub, crm=crm)
    host, port = srv.start_background("127.0.0.1", 0)
    try:
        body = json.dumps({
            "event_type": "lead_signal", "source_agent": "lead_bridge", "impact_score": 0.8,
            "payload": {"form": "deal-interest", "arm_stage": "engaged", "lead": {"email": "cto@x.eu"}},
        }).encode()
        req = urllib.request.Request(f"http://{host}:{port}/ingest", data=body,
                                     method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
        assert resp["accepted"] is True
        assert resp["crm"]["stored"] is True and resp["crm"]["forwarded"] is True
        assert srv.stats["crm_stored"] == 1 and srv.stats["crm_forwarded"] == 1
        assert store.read_text().strip()  # a line was written
        assert len(forwarded) == 1
    finally:
        srv.stop()
