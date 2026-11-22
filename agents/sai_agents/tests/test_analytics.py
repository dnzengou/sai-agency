import json
import urllib.request

from sai_agents.analytics.funnel import compute_funnel, load_leads
from sai_agents.config import Settings
from sai_agents.ingest.crm import CRMSink
from sai_agents.ingest.server import LeadIngestServer
from sai_agents.kafca.publisher import KafkaEventPublisher

LEADS = [
    {"form": "deal-alerts", "email": "a@x.eu", "region": "Nordics"},
    {"form": "deal-alerts", "email": "b@x.eu", "region": "EU"},
    {"form": "deal-alerts", "email": "c@x.eu"},
    {"form": "deal-interest", "email": "d@x.eu", "arm_stage": "engaged", "owner": "sales_gtm",
     "region": "Nordics", "deal": "Verda round", "impact_score": 0.8},
    {"form": "deal-interest", "email": "e@x.eu", "arm_stage": "engaged", "owner": "sales_gtm",
     "region": "EU", "deal": "Verda round", "impact_score": 0.7},
    {"form": "deal-interest", "email": "f@x.eu", "arm_stage": "prospect", "owner": "sales_gtm",
     "region": "Southern Europe", "deal": "EIC Accelerator", "impact_score": 0.6},
]


def test_compute_funnel_metrics():
    f = compute_funnel(LEADS)
    assert f["total_leads"] == 6
    assert f["funnel"] == {"subscribers": 3, "interests": 3, "engaged": 2, "won": 0}
    # 3 interests of 6 form fills
    assert f["conversion"]["interest_rate"] == 0.5
    # 2 engaged of 3 interests
    assert f["conversion"]["engaged_rate"] == round(2 / 3, 4)
    assert f["top_deals_by_interest"][0] == {"deal": "Verda round", "interest": 2}
    assert f["interest_by_region"]["Nordics"] == 1
    assert 0.6 <= f["avg_impact_score"] <= 0.8


def test_load_leads(tmp_path):
    p = tmp_path / "leads.ndjson"
    p.write_text("\n".join(json.dumps(l) for l in LEADS) + "\n", encoding="utf-8")
    assert len(load_leads(str(p))) == 6
    assert load_leads(None) == []
    assert load_leads(str(tmp_path / "missing.ndjson")) == []


def test_empty_funnel():
    f = compute_funnel([])
    assert f["total_leads"] == 0
    assert f["conversion"]["engaged_rate"] == 0.0


def test_analytics_endpoint(tmp_path):
    store = tmp_path / "leads.ndjson"
    store.write_text("\n".join(json.dumps(l) for l in LEADS) + "\n", encoding="utf-8")
    crm = CRMSink(store_path=str(store))
    pub = KafkaEventPublisher(Settings(kafka_enabled=False))
    srv = LeadIngestServer(Settings(kafka_enabled=False), publisher=pub, crm=crm)
    host, port = srv.start_background("127.0.0.1", 0)
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/analytics", timeout=5) as r:
            data = json.loads(r.read())
        assert data["total_leads"] == 6
        assert data["funnel"]["interests"] == 3
        assert data["lead_store"] == str(store)
    finally:
        srv.stop()
