"""RRSS sources — Redes/RSS Sources registry.

A ``DealSource`` yields raw deal dicts. The default production source reads a
bundled, curated dataset (``data/deals_seed.json``) sourced from real public
programs, tenders, accelerators, and funding rounds across Southern Europe and
the Nordics. Additional sources (RSS feeds, procurement portals, social) can be
registered without changing the pipeline — they just implement ``fetch()``.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List

from sai_agents.logging_setup import get_logger

log = get_logger("deals.sources")

# Bundled dataset ships inside the package for reproducible, offline runs.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SEED_FILE = _DATA_DIR / "deals_seed.json"


class DealSource(ABC):
    """A named source that yields raw deal dicts."""

    name: str = "source"

    @abstractmethod
    def fetch(self) -> List[Dict]:
        ...


class BundledJSONSource(DealSource):
    """Reads the curated, bundled seed dataset (real public opportunities)."""

    name = "bundled"

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _SEED_FILE

    def fetch(self) -> List[Dict]:
        if not self.path.exists():
            log.warning("deals.source.missing", path=str(self.path))
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:  # corrupt file must not crash the pipeline
            log.error("deals.source.parse_error", path=str(self.path), error=str(exc))
            return []
        deals = data.get("deals", data) if isinstance(data, dict) else data
        if not isinstance(deals, list):
            return []
        for d in deals:
            d.setdefault("source", self.name)
        log.info("deals.source.loaded", source=self.name, count=len(deals))
        return deals


class InMemorySource(DealSource):
    """Wraps a pre-built list of raw dicts — handy for tests and live feeds."""

    def __init__(self, deals: Iterable[Dict], name: str = "in_memory") -> None:
        self.name = name
        self._deals = list(deals)

    def fetch(self) -> List[Dict]:
        return list(self._deals)


class RRSSRegistry:
    """Aggregates multiple sources into one fan-in (RRSS cascade entry point)."""

    def __init__(self, sources: Iterable[DealSource] | None = None) -> None:
        self._sources: List[DealSource] = list(sources) if sources else [BundledJSONSource()]

    def register(self, source: DealSource) -> "RRSSRegistry":
        self._sources.append(source)
        return self

    @property
    def source_names(self) -> List[str]:
        return [s.name for s in self._sources]

    def fetch_all(self) -> List[Dict]:
        collected: List[Dict] = []
        for source in self._sources:
            try:
                collected.extend(source.fetch())
            except Exception as exc:  # one bad source can't sink the rest
                log.error("deals.source.error", source=source.name, error=str(exc))
        return collected
