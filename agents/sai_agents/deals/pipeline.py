"""KafCadePipeline — the KafCade cascade.

Stages (each feeds the next; failures are contained per-item):

    RRSS fetch -> normalize -> Bl screen -> dedupe -> ARM classify (+impact)
              -> publish EvolutionEvent(s) to KafCa -> export site dataset

The output is both a clean ``deals.json`` for the web app and a stream of
``DEAL_SIGNAL`` evolution events (impact-scored, Bl-guarded) for evo-metaclaw.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sai_agents.config import Settings, get_settings
from sai_agents.deals.arm import classify_arm
from sai_agents.deals.sources import RRSSRegistry
from sai_agents.kafca.blacklist import Blacklist
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import get_logger
from sai_agents.models import Deal, DealType, EventType, EvolutionEvent

log = get_logger("deals.pipeline")

_VALID_TYPES = {t.value for t in DealType}


def _normalize(raw: Dict) -> Optional[Deal]:
    """Coerce a raw source dict into a validated Deal (or drop it)."""
    if not raw or not raw.get("title"):
        return None
    data = dict(raw)
    # Map unknown/missing type to a safe default.
    dtype = str(data.get("type", "grant")).strip().lower()
    if dtype not in _VALID_TYPES:
        dtype = "partnership"
    data["type"] = dtype
    # Drop source-only keys the model doesn't accept.
    data.pop("source", None)
    try:
        return Deal(**{k: v for k, v in data.items() if k in Deal.model_fields})
    except Exception as exc:
        log.warning("deals.normalize.drop", title=data.get("title"), error=str(exc))
        return None


class KafCadePipeline:
    def __init__(
        self,
        registry: Optional[RRSSRegistry] = None,
        settings: Optional[Settings] = None,
        publisher: Optional[KafkaEventPublisher] = None,
        blacklist: Optional[Blacklist] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or RRSSRegistry()
        self.publisher = publisher or KafkaEventPublisher(self.settings)
        self.blacklist = blacklist or Blacklist(extra_patterns=self.settings.blacklist_patterns)

    # ------------------------------------------------------------------ #
    def collect(self) -> List[Deal]:
        """Run the synchronous part of the cascade: fetch → … → ARM classify."""
        raw = self.registry.fetch_all()
        normalized = [d for d in (_normalize(r) for r in raw) if d is not None]

        # Bl: drop any deal whose text trips the blacklist.
        screened: List[Deal] = []
        for deal in normalized:
            verdict = self.blacklist.screen_many([deal.title, deal.description, deal.org])
            if verdict.blocked:
                log.warning("deals.blacklisted", title=deal.title, matched=verdict.matched)
                continue
            screened.append(deal)

        # Dedupe by (title, org, country).
        seen: set[str] = set()
        deduped: List[Deal] = []
        for deal in screened:
            key = deal.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(classify_arm(deal))

        # Highest impact first — evo-metaclaw prioritisation order.
        deduped.sort(key=lambda d: d.impact_score, reverse=True)
        log.info(
            "deals.collected",
            sources=self.registry.source_names,
            raw=len(raw),
            kept=len(deduped),
        )
        return deduped

    # ------------------------------------------------------------------ #
    async def publish(self, deals: List[Deal]) -> int:
        """Publish each deal as an impact-scored DEAL_SIGNAL evolution event."""
        events: List[EvolutionEvent] = [
            EvolutionEvent(
                event_type=EventType.DEAL_SIGNAL,
                service=self.settings.service_name,
                source_agent="deal_sourcing",
                impact_score=deal.impact_score,
                payload=deal.model_dump(mode="json"),
            )
            for deal in deals
        ]
        return await self.publisher.publish_many(events)

    async def run(self, export_path: Optional[Path | str] = None) -> Dict:
        """Full cascade: collect → publish to KafCa → export site dataset."""
        deals = self.collect()
        await self.publisher.start()
        try:
            published = await self.publish(deals)
        finally:
            await self.publisher.stop()

        dataset = self.build_dataset(deals)
        if export_path is not None:
            self.export(dataset, export_path)
        return {
            "deals": len(deals),
            "published": published,
            "high_impact": len(self.publisher.high_impact_events()),
            "dataset": dataset,
        }

    # ------------------------------------------------------------------ #
    def build_dataset(self, deals: List[Deal]) -> Dict:
        """Shape deals + rollup summary for the web app to consume."""
        by_country: Dict[str, int] = {}
        by_type: Dict[str, float] = {}
        by_region: Dict[str, int] = {}
        total_value = 0.0
        open_count = 0
        for d in deals:
            by_country[d.country] = by_country.get(d.country, 0) + 1
            by_region[d.region] = by_region.get(d.region, 0) + 1
            by_type[d.type.value] = by_type.get(d.type.value, 0.0) + (d.value_eur or 0.0)
            total_value += d.value_eur or 0.0
            if d.stage in ("open", "upcoming"):
                open_count += 1
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "service": self.settings.service_name,
            "schema_version": 1,
            "summary": {
                "total_deals": len(deals),
                "open_or_upcoming": open_count,
                "total_pipeline_value_eur": round(total_value, 2),
                "countries": sorted(k for k in by_country if k),
                "regions": sorted(k for k in by_region if k),
                "by_country": by_country,
                "by_region": by_region,
                "pipeline_value_by_type_eur": {k: round(v, 2) for k, v in by_type.items()},
            },
            "deals": [d.model_dump(mode="json") for d in deals],
        }

    @staticmethod
    def export(dataset: Dict, path: Path | str) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("deals.exported", path=str(out), deals=len(dataset.get("deals", [])))
        return out
