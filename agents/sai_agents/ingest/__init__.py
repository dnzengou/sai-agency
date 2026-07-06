"""Lightweight HTTP ingest endpoint — the target for the Netlify lead-bridge's
``KAFCA_WEBHOOK_URL``. Accepts EvolutionEvents (e.g. LEAD_SIGNAL) over HTTP and
publishes them to the KafCa stream."""

from sai_agents.ingest.server import LeadIngestServer, coerce_event

__all__ = ["LeadIngestServer", "coerce_event"]
