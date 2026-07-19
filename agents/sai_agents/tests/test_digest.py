import json

from sai_agents.digest.builder import build_digest, select_deals
from sai_agents.digest.sender import DigestSender, SMTPConfig
from sai_agents.digest.subscribers import (
    collect_subscribers,
    from_lead_store,
    from_netlify,
)

DATASET = {
    "deals": [
        {"id": "a1", "title": "Open Grant", "org": "EIC", "country": "EU", "region": "EU",
         "type": "grant", "value_eur": 1000000, "stage": "open", "impact_score": 0.6,
         "description": "An open EU grant.", "deadline": "2026-09-01"},
        {"id": "b2", "title": "Closed Round", "org": "Acme", "country": "Sweden", "region": "Nordics",
         "type": "funding_round", "value_eur": 5000000, "stage": "announced", "impact_score": 0.9,
         "description": "A closed round."},
        {"id": "c3", "title": "Upcoming Tender", "org": "Gov", "country": "Spain", "region": "Southern Europe",
         "type": "public_tender", "stage": "upcoming", "impact_score": 0.5, "description": "A tender."},
    ]
}


def test_select_prioritises_open_then_impact():
    picked = select_deals(DATASET, limit=10)
    # open/upcoming first (a1 open, c3 upcoming) then announced (b2)
    assert [d["id"] for d in picked][:2] == ["a1", "c3"] or [d["id"] for d in picked][:2] == ["c3", "a1"]
    assert picked[-1]["id"] == "b2"


def test_region_filter_and_limit():
    picked = select_deals(DATASET, region="Nordics", limit=5)
    assert [d["id"] for d in picked] == ["b2"]


def test_build_digest_html_and_text():
    subject, html, text = build_digest(DATASET, limit=3)
    assert "Deal Radar" in subject and "3" in subject
    assert "Open Grant" in html and "/deals/a1" in html
    assert "See all deals" in html
    assert "Open Grant" in text and "/deals/a1" in text
    # deal links point to detail pages
    assert "https://sai-agency.netlify.app/deals/a1" in html


def test_subscribers_from_lead_store_dedup(tmp_path):
    store = tmp_path / "leads.ndjson"
    store.write_text("\n".join([
        json.dumps({"form": "deal-alerts", "email": "a@x.eu", "region": "Nordics"}),
        json.dumps({"form": "deal-alerts", "email": "A@x.eu"}),  # dup (case-insensitive)
        json.dumps({"form": "deal-interest", "email": "b@x.eu"}),  # not an alert sub
        json.dumps({"form": "deal-alerts", "email": "not-an-email"}),  # invalid
    ]), encoding="utf-8")
    subs = from_lead_store(str(store))
    assert [s["email"] for s in subs] == ["a@x.eu", "A@x.eu"]
    merged = collect_subscribers(env={"SAI_LEAD_STORE": str(store)})
    assert [s["email"] for s in merged] == ["a@x.eu"]  # deduped


def test_subscribers_from_netlify_injected_fetcher():
    body = json.dumps([
        {"data": {"email": "c@x.eu", "region": "EU"}},
        {"data": {"email": "bad"}},
    ])
    subs = from_netlify("tok", "form123", fetcher=lambda url, headers: body)
    assert [s["email"] for s in subs] == ["c@x.eu"]


def test_sender_dry_run_writes_preview(tmp_path):
    preview = tmp_path / "preview.html"
    sender = DigestSender(config=SMTPConfig(host=""), preview_path=str(preview))
    res = sender.send([{"email": "a@x.eu"}, {"email": "b@x.eu"}], "S", "<b>hi</b>", "hi")
    assert res["dry_run"] == 2 and res["sent"] == 0
    assert preview.read_text() == "<b>hi</b>"


def test_sender_smtp_uses_injected_transport():
    sent = []

    class FakeSMTP:
        def __init__(self, host, port): sent.append(("connect", host, port))
        def starttls(self): sent.append(("starttls",))
        def login(self, u, p): sent.append(("login", u))
        def send_message(self, msg): sent.append(("send", msg["To"]))
        def quit(self): sent.append(("quit",))

    cfg = SMTPConfig(host="smtp.x", port=587, user="u", password="p", starttls=True)
    sender = DigestSender(config=cfg, smtp_factory=lambda h, p: FakeSMTP(h, p))
    res = sender.send([{"email": "a@x.eu"}, {"email": "b@x.eu"}], "S", "<b>h</b>", "h")
    assert res["sent"] == 2 and res["failed"] == 0
    assert ("send", "a@x.eu") in sent and ("login", "u") in sent
