"""LeadIngestServer — a lightweight, dependency-free HTTP ingest endpoint.

It is the concrete target for the Netlify lead-bridge's ``KAFCA_WEBHOOK_URL``:
it accepts EvolutionEvents (typically ``LEAD_SIGNAL``) over HTTP and publishes
them to the KafCa stream via the shared ``KafkaEventPublisher`` (Bl blacklist +
circuit breaker + impact tracking all still apply).

Design:
  * stdlib ``http.server`` only — no aiohttp/FastAPI/uvicorn. Requests are
    handled on a threading server; the async publisher runs on a dedicated
    background event loop and coroutines are marshalled across via
    ``run_coroutine_threadsafe``.
  * Optional bearer-token auth (``SAI_INGEST_TOKEN``).
  * Routes:
      GET  /health  -> {"ok": true, "kafka_active": bool, "stats": {...}}
      POST /ingest  -> {"accepted": bool, "event_id": str, "reason"?: str}

Run: ``python -m sai_agents.ingest.server`` (or the ``sai-ingest`` script).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from sai_agents.config import Settings, get_settings
from sai_agents.ingest.crm import CRMSink
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import configure_logging, get_logger
from sai_agents.models import EventType, EvolutionEvent

log = get_logger("ingest.server")

_MAX_BODY_BYTES = 64 * 1024  # reject anything larger — leads are tiny


def coerce_event(body: Dict[str, Any]) -> EvolutionEvent:
    """Turn an incoming JSON object into a validated EvolutionEvent.

    Accepts either a full EvolutionEvent envelope (has ``event_type``) or a bare
    lead payload, which is wrapped as a LEAD_SIGNAL event.
    """
    if isinstance(body, dict) and "event_type" in body:
        allowed = {k: v for k, v in body.items() if k in EvolutionEvent.model_fields}
        return EvolutionEvent(**allowed)
    impact = 0.5
    if isinstance(body, dict):
        try:
            impact = float(body.get("impact_score", 0.5))
        except (TypeError, ValueError):
            impact = 0.5
    return EvolutionEvent(
        event_type=EventType.LEAD_SIGNAL,
        source_agent="lead_bridge",
        impact_score=impact,
        payload=body if isinstance(body, dict) else {"value": body},
    )


class LeadIngestServer:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        publisher: Optional[KafkaEventPublisher] = None,
        token: Optional[str] = None,
        crm: Optional[CRMSink] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.publisher = publisher or KafkaEventPublisher(self.settings)
        self.token = token if token is not None else os.getenv("SAI_INGEST_TOKEN", "")
        self.crm = crm if crm is not None else CRMSink(
            store_path=os.getenv("SAI_LEAD_STORE"),
            webhook_url=os.getenv("CRM_WEBHOOK_URL"),
            webhook_token=os.getenv("CRM_WEBHOOK_TOKEN"),
        )
        self.stats = {"received": 0, "accepted": 0, "rejected": 0, "crm_stored": 0, "crm_forwarded": 0}
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, name="ingest-loop", daemon=True)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._started = False

    # -- async loop plumbing --------------------------------------------- #
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self) -> None:
        if self._started:
            return
        self._loop_thread.start()
        asyncio.run_coroutine_threadsafe(self.publisher.start(), self._loop).result(timeout=10)
        self._started = True

    def _publish(self, event: EvolutionEvent) -> bool:
        return asyncio.run_coroutine_threadsafe(
            self.publisher.publish(event), self._loop
        ).result(timeout=10)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
        if self._started:
            try:
                asyncio.run_coroutine_threadsafe(self.publisher.stop(), self._loop).result(timeout=5)
            except Exception:  # pragma: no cover
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    # -- request handling ------------------------------------------------ #
    def _handle_ingest(self, body: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        self.stats["received"] += 1
        try:
            event = coerce_event(body)
        except Exception as exc:
            self.stats["rejected"] += 1
            return 400, {"accepted": False, "reason": f"invalid event: {exc}"}
        accepted = self._publish(event)
        if accepted:
            self.stats["accepted"] += 1
        else:
            self.stats["rejected"] += 1  # blacklist or circuit breaker
        resp = {"accepted": accepted, "event_id": event.event_id}

        # CRM sink: durable store + optional webhook forward for real leads.
        if accepted and event.event_type == EventType.LEAD_SIGNAL and self.crm.enabled:
            try:
                crm_result = self.crm.record(event)
                self.stats["crm_stored"] += int(crm_result["stored"])
                self.stats["crm_forwarded"] += int(crm_result["forwarded"])
                resp["crm"] = crm_result
            except Exception as exc:  # never fail the request on a CRM hiccup
                log.error("ingest.crm_error", error=str(exc))
        return 200, resp

    def make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):  # silence default stderr logging
                pass

            def _send(self, code: int, obj: Dict[str, Any]) -> None:
                payload = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _authed(self) -> bool:
                if not server.token:
                    return True
                header = self.headers.get("Authorization", "")
                return header == f"Bearer {server.token}"

            def do_GET(self):
                if self.path.split("?")[0] != "/health":
                    return self._send(404, {"error": "not found"})
                self._send(200, {
                    "ok": True,
                    "service": server.settings.service_name,
                    "kafka_active": server.publisher.kafka_active,
                    "stats": server.stats,
                })

            def do_POST(self):
                if self.path.split("?")[0] != "/ingest":
                    return self._send(404, {"error": "not found"})
                if not self._authed():
                    return self._send(401, {"error": "unauthorized"})
                try:
                    length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    return self._send(400, {"error": "bad content-length"})
                if length <= 0 or length > _MAX_BODY_BYTES:
                    return self._send(413, {"error": "empty or too large"})
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    return self._send(400, {"accepted": False, "reason": "invalid JSON"})
                code, resp = server._handle_ingest(body)
                log.info("ingest.request", accepted=resp.get("accepted"), code=code)
                self._send(code, resp)

        return Handler

    def start_background(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        """Start the publisher + HTTP server on a background thread.

        Returns the bound ``(host, port)`` (use ``port=0`` for an ephemeral
        port, e.g. in tests). Call :meth:`stop` to shut down.
        """
        self.start()
        self._httpd = ThreadingHTTPServer((host, port), self.make_handler())
        bound = self._httpd.server_address
        thread = threading.Thread(target=self._httpd.serve_forever, name="ingest-http", daemon=True)
        thread.start()
        log.info("ingest.serving", host=bound[0], port=bound[1], auth=bool(self.token))
        return bound[0], bound[1]

    def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Blocking serve loop. Starts the publisher first."""
        self.start_background(host, port)
        try:
            while True:
                self._loop_thread.join(timeout=1.0)
        except KeyboardInterrupt:  # pragma: no cover
            pass
        finally:
            self.stop()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    host = os.getenv("SAI_INGEST_HOST", "0.0.0.0")
    port = int(os.getenv("SAI_INGEST_PORT", "8080"))
    LeadIngestServer(settings).serve(host, port)


if __name__ == "__main__":
    main()
