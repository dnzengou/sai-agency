"""KafCadePipeline — the KafCade cascade.

Stages (each feeds the next; failures are contained per-item):

    RRSS fetch -> normalize -> Bl screen -> dedupe -> ARM classify (+impact)
              -> publish EvolutionEvent(s) to KafCa -> export site dataset

The output is both a clean ``deals.json`` for the web app and a stream of
``DEAL_SIGNAL`` evolution events (impact-scored, Bl-guarded) for evo-metaclaw.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

from sai_agents.config import Settings, get_settings
from sai_agents.deals.arm import arm_priority, arm_rationale, classify_arm
from sai_agents.valuation.estimator import estimate_value
from sai_agents.deals.rss import rss_sources_from_feeds
from sai_agents.deals.sources import BundledJSONSource, RRSSRegistry
from sai_agents.kafca.blacklist import Blacklist
from sai_agents.kafca.publisher import KafkaEventPublisher
from sai_agents.logging_setup import get_logger
from sai_agents.models import Deal, DealCategory, DealType, EventType, EvolutionEvent

log = get_logger("deals.pipeline")

_VALID_TYPES = {t.value for t in DealType}
_VALID_CATEGORIES = {c.value for c in DealCategory}

# Map source-provided type synonyms onto canonical DealTypes.
_TYPE_SYNONYMS = {
    "incentive": "grant",
    "relocation": "property_scheme",
    "one_euro_house": "property_scheme",
    "house_scheme": "property_scheme",
    "marketplace": "business_succession",
    "business_for_sale": "business_succession",
    "succession": "business_succession",
    # Venture family — kept as its own type.
    "search_fund": "venture",
    "eta": "venture",
    "community_ownership": "venture",
    "co_investment": "venture",
    "crowdfunding": "venture",
    "fund": "venture",
}

# Types that imply a category when the source didn't state one.
_CATEGORY_BY_TYPE = {
    "property_scheme": "repopulation",
    "business_succession": "succession",
}


def _infer_category(data: Dict, dtype: str) -> str:
    cat = str(data.get("category", "")).strip().lower()
    if cat in _VALID_CATEGORIES:
        return cat
    return _CATEGORY_BY_TYPE.get(dtype, "ai_ml")


def _normalize(raw: Dict) -> Optional[Deal]:
    """Coerce a raw source dict into a validated Deal (or drop it)."""
    if not raw or not raw.get("title"):
        return None
    data = dict(raw)
    # Normalise type: apply synonyms, then fall back to a safe default.
    dtype = str(data.get("type", "grant")).strip().lower()
    dtype = _TYPE_SYNONYMS.get(dtype, dtype)
    if dtype not in _VALID_TYPES:
        dtype = "partnership"
    data["type"] = dtype
    data["category"] = _infer_category(data, dtype)
    # A venture-category item typed as a succession marketplace is really a
    # venture vehicle — relabel so the type matches the category.
    if data["category"] == "venture" and dtype == "business_succession":
        data["type"] = "venture"
    # Drop source-only keys the model doesn't accept.
    data.pop("source", None)
    try:
        deal = Deal(**{k: v for k, v in data.items() if k in Deal.model_fields})
    except Exception as exc:
        log.warning("deals.normalize.drop", title=data.get("title"), error=str(exc))
        return None
    # Deterministic, content-derived id so regenerating the same data yields a
    # stable deals.json (the scheduled refresh only commits real changes).
    deal.id = hashlib.sha1(deal.dedupe_key().encode("utf-8")).hexdigest()[:16]
    return deal


class KafCadePipeline:
    def __init__(
        self,
        registry: Optional[RRSSRegistry] = None,
        settings: Optional[Settings] = None,
        publisher: Optional[KafkaEventPublisher] = None,
        blacklist: Optional[Blacklist] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or self._default_registry()
        self.publisher = publisher or KafkaEventPublisher(self.settings)
        self.blacklist = blacklist or Blacklist(extra_patterns=self.settings.blacklist_patterns)

    def _default_registry(self) -> RRSSRegistry:
        """Bundled curated dataset + any opt-in live RSS feeds (RRSS)."""
        sources = [BundledJSONSource()]
        if self.settings.rss_feeds:
            # Keep only in-coverage regions from generic feeds.
            sources.extend(
                rss_sources_from_feeds(
                    self.settings.rss_feeds,
                    region_filter={
                        "Southern Europe", "Nordics", "Western Europe", "EU",
                        "Central Europe", "East Africa", "North America",
                        "US East Coast", "US West Coast",
                    },
                )
            )
        return RRSSRegistry(sources)

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
            deal = classify_arm(deal)
            deal.valuation = estimate_value(deal)
            deduped.append(deal)

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
        rss_path: Optional[Path] = None
        if export_path is not None:
            self.export(dataset, export_path)
            # RRSS: also emit an RSS 2.0 feed next to the JSON.
            rss_path = Path(export_path).with_suffix(".xml")
            self.export_rss(dataset, rss_path)
        return {
            "deals": len(deals),
            "published": published,
            "high_impact": len(self.publisher.high_impact_events()),
            "dataset": dataset,
            "rss_path": str(rss_path) if rss_path else None,
        }

    # ------------------------------------------------------------------ #
    def _load_champion(self):
        """Load the evolved deal_sourcing champion spec + skill loadout so the
        public dataset is ordered by evolved ARM priority. Fail-safe: any error
        or an unevolved store yields (None, []) — pure impact order, unchanged.
        """
        if not getattr(self.settings, "evo_specs_enabled", True):
            return None, []
        try:
            from sai_agents.evoforge import EvoForge
            from sai_agents.evometaclaw.trajectory import TrajectoryStore
            from sai_agents.evoskillopt import EvoSkillOpt

            root = TrajectoryStore().root
            pop = root / "_population.json"
            skl = root / "_skills.json"
            spec = (
                EvoForge(population_path=pop).champion_specs().get("deal_sourcing")
                if pop.exists()
                else None
            )
            loadout = EvoSkillOpt(skills_path=skl).current_loadout(5) if skl.exists() else []
            return spec, loadout
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("deals.champion_load.failed", error=str(exc))
            return None, []

    # ------------------------------------------------------------------ #
    def build_dataset(self, deals: List[Deal]) -> Dict:
        """Shape deals + rollup summary for the web app to consume."""
        # Evolved ARM priority: order the public dataset the way evolution has
        # learned to, and expose the score per deal for the site's sort.
        champ_spec, champ_loadout = self._load_champion()
        deals = sorted(
            deals, key=lambda d: arm_priority(d, champ_spec, champ_loadout), reverse=True
        )
        by_country: Dict[str, int] = {}
        by_type: Dict[str, float] = {}
        by_region: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        total_value = 0.0
        open_count = 0
        for d in deals:
            by_country[d.country] = by_country.get(d.country, 0) + 1
            by_region[d.region] = by_region.get(d.region, 0) + 1
            by_category[d.category.value] = by_category.get(d.category.value, 0) + 1
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
                "categories": sorted(k for k in by_category if k),
                "by_country": by_country,
                "by_region": by_region,
                "by_category": by_category,
                "pipeline_value_by_type_eur": {k: round(v, 2) for k, v in by_type.items()},
                "arm": self.arm_summary(deals),
                "evolved_order": bool(champ_spec or champ_loadout),
            },
            "deals": [
                {
                    **d.model_dump(mode="json"),
                    "arm_priority": arm_priority(d, champ_spec, champ_loadout),
                    "arm_rationale": arm_rationale(d, champ_spec, champ_loadout),
                }
                for d in deals
            ],
        }

    # ------------------------------------------------------------------ #
    # Bi: ARM portfolio intelligence rollup (Business / Property / Deals).
    # ------------------------------------------------------------------ #
    # The B/P/D/V portfolio dimensions the web app groups deals under.
    _PORTFOLIO_DIMENSIONS = {
        "business": ("succession",),
        "property": ("repopulation",),
        "ai_deals": ("ai_ml",),
        "ventures": ("venture",),
    }

    @staticmethod
    def arm_summary(deals: List[Deal]) -> Dict:
        """Roll ARM-classified deals up into a portfolio-intelligence view.

        Surfaces the pipeline the way an operator works it: how deals distribute
        across ARM stages, who owns them, the next-action queue, and the value /
        openness of each Business / Property / AI-deal / Venture dimension.
        """
        by_arm_stage: Dict[str, int] = {}
        by_owner: Dict[str, int] = {}
        next_actions: Dict[str, int] = {}
        cat_roll: Dict[str, Dict[str, float]] = {}
        for d in deals:
            by_arm_stage[d.arm_stage.value] = by_arm_stage.get(d.arm_stage.value, 0) + 1
            by_owner[d.owner] = by_owner.get(d.owner, 0) + 1
            if d.next_action:
                next_actions[d.next_action] = next_actions.get(d.next_action, 0) + 1
            c = cat_roll.setdefault(
                d.category.value, {"count": 0, "value_eur": 0.0, "open": 0, "impact_sum": 0.0}
            )
            c["count"] += 1
            c["value_eur"] += d.value_eur or 0.0
            c["impact_sum"] += d.impact_score
            if d.stage in ("open", "upcoming"):
                c["open"] += 1

        def finalize(cats) -> Dict[str, float]:
            count = sum(cat_roll.get(c, {}).get("count", 0) for c in cats)
            value = sum(cat_roll.get(c, {}).get("value_eur", 0.0) for c in cats)
            openc = sum(cat_roll.get(c, {}).get("open", 0) for c in cats)
            isum = sum(cat_roll.get(c, {}).get("impact_sum", 0.0) for c in cats)
            return {
                "count": count,
                "value_eur": round(value, 2),
                "open": openc,
                "avg_impact": round(isum / count, 4) if count else 0.0,
            }

        # Highest-impact open deal per owner — the "work this next" shortlist.
        top_actions = sorted(next_actions.items(), key=lambda kv: kv[1], reverse=True)[:8]
        return {
            "by_arm_stage": by_arm_stage,
            "by_owner": by_owner,
            "next_action_queue": [{"action": a, "count": n} for a, n in top_actions],
            "portfolio": {
                dim: finalize(cats) for dim, cats in KafCadePipeline._PORTFOLIO_DIMENSIONS.items()
            },
        }

    @staticmethod
    def export(dataset: Dict, path: Path | str) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("deals.exported", path=str(out), deals=len(dataset.get("deals", [])))
        return out

    # ------------------------------------------------------------------ #
    # RRSS output — an actual RSS 2.0 feed for distribution/subscription.
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_rss(
        dataset: Dict,
        site_url: str = "https://sai-agency-deals-radar.netlify.app",
    ) -> str:
        deals = dataset.get("deals", [])
        try:
            build_dt = parsedate_to_datetime(format_datetime(datetime.fromisoformat(dataset["generated_at"])))
        except Exception:
            build_dt = datetime.now(timezone.utc)
        items = []
        for d in deals:
            link = d.get("source_url") or f"{site_url}/deals"
            parts = [
                d.get("description", ""),
                f"Type: {d.get('type', '')}",
                f"Country: {d.get('country', '')} ({d.get('region', '')})",
                f"Value: {d.get('value_eur') or 'n/a'}",
                f"Impact: {d.get('impact_score', '')}",
            ]
            desc = " · ".join(p for p in parts if p)
            items.append(
                "    <item>\n"
                f"      <title>{escape(str(d.get('title', '')))}</title>\n"
                f"      <link>{escape(link)}</link>\n"
                f"      <guid isPermaLink=\"false\">{escape(str(d.get('id', link)))}</guid>\n"
                f"      <category>{escape(str(d.get('type', '')))}</category>\n"
                f"      <description>{escape(desc)}</description>\n"
                "    </item>"
            )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0">\n  <channel>\n'
            "    <title>SAI Agency — Deal Radar</title>\n"
            f"    <link>{site_url}/deals</link>\n"
            "    <description>Real, sourced AI/ML/data opportunities across "
            "Southern Europe and the Nordics.</description>\n"
            "    <language>en</language>\n"
            f"    <lastBuildDate>{format_datetime(build_dt)}</lastBuildDate>\n"
            f"    <atom:link xmlns:atom=\"http://www.w3.org/2005/Atom\" href=\"{site_url}/deals.xml\" rel=\"self\" type=\"application/rss+xml\" />\n"
            + "\n".join(items)
            + "\n  </channel>\n</rss>\n"
        )

    @staticmethod
    def export_rss(dataset: Dict, path: Path | str, site_url: str = "https://sai-agency-deals-radar.netlify.app") -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(KafCadePipeline.build_rss(dataset, site_url), encoding="utf-8")
        log.info("deals.rss_exported", path=str(out), deals=len(dataset.get("deals", [])))
        return out
