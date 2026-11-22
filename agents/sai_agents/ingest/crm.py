"""CRMSink — vendor-neutral lead sink for the ingest endpoint.

Every accepted ``LEAD_SIGNAL`` can be:
  * appended to a durable NDJSON lead store (``SAI_LEAD_STORE``) — always-on,
    replayable, importable into any CRM/spreadsheet; and
  * forwarded to a configurable CRM webhook (``CRM_WEBHOOK_URL``) as a flat JSON
    lead record — compatible with HubSpot/Pipedrive workflows, Zapier/Make, or a
    Google-Sheets webhook. Optional bearer token (``CRM_WEBHOOK_TOKEN``).

Both are optional and independent. Failures never drop the lead (it is already
in the KafCa stream); they are logged and reported back.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Optional

from sai_agents.logging_setup import get_logger
from sai_agents.models import EvolutionEvent

log = get_logger("ingest.crm")

_LEAD_KEYS = ("name", "email", "company", "message", "deal", "deal_url", "region")


def event_to_lead(event: EvolutionEvent) -> Dict:
    """Flatten a LEAD_SIGNAL event into a CRM-friendly record."""
    payload = event.payload or {}
    lead = payload.get("lead", {}) if isinstance(payload.get("lead"), dict) else {}
    record = {
        "received_at": event.timestamp,
        "event_id": event.event_id,
        "form": payload.get("form"),
        "impact_score": event.impact_score,
        "arm_stage": payload.get("arm_stage"),
        "owner": payload.get("owner"),
        "priority": payload.get("priority"),
        "next_action": payload.get("next_action"),
    }
    for k in _LEAD_KEYS:
        if k in lead:
            record[k] = lead[k]
    return record


def _default_post(url: str, body: bytes, headers: Dict[str, str], timeout: float) -> int:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.status


class CRMSink:
    def __init__(
        self,
        store_path: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_token: Optional[str] = None,
        timeout: float = 10.0,
        poster: Optional[Callable[[str, bytes, Dict[str, str], float], int]] = None,
    ) -> None:
        self.store_path = Path(store_path) if store_path else None
        self.webhook_url = webhook_url or None
        self.webhook_token = webhook_token or None
        self.timeout = timeout
        self._post = poster or _default_post

    @property
    def enabled(self) -> bool:
        return bool(self.store_path or self.webhook_url)

    def record(self, event: EvolutionEvent) -> Dict:
        lead = event_to_lead(event)
        return {
            "stored": self._append(lead),
            "forwarded": self._forward(lead),
        }

    def _append(self, lead: Dict) -> bool:
        if not self.store_path:
            return False
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with self.store_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(lead, ensure_ascii=False) + "\n")
            return True
        except Exception as exc:  # pragma: no cover - fs error path
            log.error("crm.store_failed", error=str(exc), path=str(self.store_path))
            return False

    def _forward(self, lead: Dict) -> bool:
        if not self.webhook_url:
            return False
        headers = {"Content-Type": "application/json"}
        if self.webhook_token:
            headers["Authorization"] = f"Bearer {self.webhook_token}"
        try:
            status = self._post(self.webhook_url, json.dumps(lead).encode("utf-8"), headers, self.timeout)
            if not (200 <= status < 300):
                raise RuntimeError(f"HTTP {status}")
            log.info("crm.forwarded", event_id=lead.get("event_id"), email=lead.get("email"))
            return True
        except Exception as exc:
            log.error("crm.forward_failed", error=str(exc), event_id=lead.get("event_id"))
            return False
