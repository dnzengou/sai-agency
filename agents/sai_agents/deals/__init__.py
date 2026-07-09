"""Deal sourcing — KafCade cascade over RRSS sources with ARM classification.

KafCade = a cascade of KafCa stages: source (RRSS) -> normalize -> dedupe ->
impact-score -> ARM-classify -> publish. RRSS = Redes/RSS Sources: a registry of
pluggable feeds (bundled dataset, RSS, social, procurement portals).
ARM = Account & Relationship Management (pipeline stage, owner, next action).
"""

from sai_agents.deals.arm import classify_arm, score_deal_impact
from sai_agents.deals.deal_sourcing_agent import DealSourcingAgent
from sai_agents.deals.pipeline import KafCadePipeline
from sai_agents.deals.rss import RSSSource, parse_feed, rss_sources_from_feeds
from sai_agents.deals.sources import (
    BundledJSONSource,
    DealSource,
    RRSSRegistry,
)

__all__ = [
    "DealSource",
    "BundledJSONSource",
    "RRSSRegistry",
    "RSSSource",
    "parse_feed",
    "rss_sources_from_feeds",
    "classify_arm",
    "score_deal_impact",
    "KafCadePipeline",
    "DealSourcingAgent",
]
