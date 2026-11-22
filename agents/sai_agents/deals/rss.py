"""Live RSS/Atom deal source (RRSS) + a keyword classifier.

RSS items are generic news, so a raw item is mapped to a structured deal via
lightweight heuristics: infer ``type`` (funding round / grant / tender /
accelerator / partnership), ``sector``, and ``country``/``region`` by scanning
the title + description. RSS-derived deals carry a lower ``confidence`` than the
curated bundled dataset, and the pipeline's Bl/dedupe/ARM stages still apply.

Network is opt-in: the pipeline only adds RSS sources when ``SAI_RSS_FEEDS`` is
set, so default runs stay offline-deterministic.
"""

from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, Optional

from sai_agents.deals.sources import DealSource
from sai_agents.logging_setup import get_logger

log = get_logger("deals.rss")

# --- classifier tables -------------------------------------------------- #
_TYPE_PATTERNS = [
    ("funding_round", re.compile(r"\b(raise[sd]?|raising|series\s+[a-e]\b|pre-?seed|seed round|secures?\s+€|closes?\s+.*(round|funding)|valuation)\b", re.I)),
    ("public_tender", re.compile(r"\b(tender|procurement|rfp|request for proposal|contract notice|call for tenders)\b", re.I)),
    ("accelerator", re.compile(r"\b(accelerator|incubator|cohort|bootcamp|programme intake|program intake)\b", re.I)),
    ("grant", re.compile(r"\b(grant|call for proposals|funding call|subsidy|co-?funded|cascade funding|open call)\b", re.I)),
    ("partnership", re.compile(r"\b(partnership|alliance|joins forces|collaboration|consortium|memorandum of understanding|mou)\b", re.I)),
]

_SECTOR_PATTERNS = [
    ("HealthTech", re.compile(r"\b(health|clinical|patient|medical|biotech|diagnos)", re.I)),
    ("LegalTech", re.compile(r"\b(legal|law firm|lawyer|compliance)\b", re.I)),
    ("Data infrastructure", re.compile(r"\b(cloud|gpu|compute|data cent|infrastructure|supercomput|hpc)\b", re.I)),
    ("GovTech", re.compile(r"\b(government|public sector|municipal|govtech|ministry)\b", re.I)),
    ("Climate", re.compile(r"\b(climate|energy|carbon|renewable|sustainab)\b", re.I)),
    ("Fintech", re.compile(r"\b(fintech|payments|banking|insurance|insurtech)\b", re.I)),
    ("Industrial AI", re.compile(r"\b(manufactur|industrial|factory|robot|supply chain)\b", re.I)),
]

_REGION_COUNTRIES = {
    "Southern Europe": ["Spain", "Italy", "Portugal", "Greece", "Croatia", "Slovenia", "Cyprus", "Malta"],
    "Nordics": ["Sweden", "Norway", "Denmark", "Finland", "Iceland"],
}

# Country -> match terms (name + demonym + major cities) so RSS prose like
# "Swedish", "Stockholm-based", or "Helsinki firm" resolves to a country.
_COUNTRY_SYNONYMS = {
    "Sweden": ["Sweden", "Swedish", "Stockholm", "Gothenburg", "Malmö", "Malmo", "Uppsala"],
    "Norway": ["Norway", "Norwegian", "Oslo", "Bergen", "Trondheim"],
    "Denmark": ["Denmark", "Danish", "Copenhagen", "Aarhus", "Odense"],
    "Finland": ["Finland", "Finnish", "Helsinki", "Espoo", "Tampere", "Oulu"],
    "Iceland": ["Iceland", "Icelandic", "Reykjavik", "Reykjavík"],
    "Spain": ["Spain", "Spanish", "Madrid", "Barcelona", "Valencia", "Bilbao", "Sevilla", "San Sebastián", "San Sebastian"],
    "Italy": ["Italy", "Italian", "Rome", "Milan", "Milano", "Turin", "Naples", "Bologna"],
    "Portugal": ["Portugal", "Portuguese", "Lisbon", "Lisboa", "Porto"],
    "Greece": ["Greece", "Greek", "Athens", "Thessaloniki"],
    "Croatia": ["Croatia", "Croatian", "Zagreb", "Split"],
    "Slovenia": ["Slovenia", "Slovenian", "Ljubljana", "Maribor"],
    "Cyprus": ["Cyprus", "Cypriot", "Nicosia", "Limassol"],
    "Malta": ["Malta", "Maltese", "Valletta"],
}
_COUNTRY_RE = {
    country: re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
    for country, terms in _COUNTRY_SYNONYMS.items()
}


def classify_type(text: str) -> str:
    for dtype, rx in _TYPE_PATTERNS:
        if rx.search(text):
            return dtype
    return "partnership"


def classify_sector(text: str) -> str:
    for sector, rx in _SECTOR_PATTERNS:
        if rx.search(text):
            return sector
    return "AI/ML"


def infer_country_region(text: str) -> tuple[str, str]:
    for country, rx in _COUNTRY_RE.items():
        if rx.search(text):
            for region, countries in _REGION_COUNTRIES.items():
                if country in countries:
                    return country, region
    return "", "EU"


# --- feed parsing ------------------------------------------------------- #
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml_text: str, source_name: str = "rss") -> List[Dict]:
    """Parse an RSS 2.0 or Atom feed into raw deal dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("deals.rss.parse_error", source=source_name, error=str(exc))
        return []

    raw: List[Dict] = []
    # RSS 2.0: rss/channel/item
    items = root.findall(".//item")
    if items:
        for it in items:
            title = _text(it.find("title"))
            desc = re.sub(r"<[^>]+>", " ", _text(it.find("description")))
            link = _text(it.find("link"))
            date = _text(it.find("pubDate"))
            raw.append(_to_deal(title, desc, link, date, source_name))
    else:
        # Atom: feed/entry
        for e in root.findall(f"{_ATOM}entry"):
            title = _text(e.find(f"{_ATOM}title"))
            desc = re.sub(r"<[^>]+>", " ", _text(e.find(f"{_ATOM}summary")) or _text(e.find(f"{_ATOM}content")))
            link_el = e.find(f"{_ATOM}link")
            link = link_el.get("href", "") if link_el is not None else ""
            date = _text(e.find(f"{_ATOM}updated"))
            raw.append(_to_deal(title, desc, link, date, source_name))
    return [d for d in raw if d.get("title")]


def _to_deal(title: str, desc: str, link: str, date: str, source_name: str) -> Dict:
    text = f"{title}. {desc}"
    country, region = infer_country_region(text)
    return {
        "title": title,
        "org": "",
        "country": country,
        "region": region,
        "sector": classify_sector(text),
        "type": classify_type(text),
        "value_eur": None,
        "stage": "announced",
        "deadline": None,
        "date": date or None,
        "source_url": link,
        "source_name": source_name,
        "description": desc[:400],
        "confidence": 0.4,
    }


def _default_fetch(url: str, timeout: float = 10.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "sai-agents-rss/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


class RSSSource(DealSource):
    """A DealSource backed by a live RSS/Atom feed URL.

    ``fetcher`` is injectable so tests never hit the network. Set
    ``region_filter`` to keep only items whose inferred region is in the set
    (e.g. drop non-EU items).
    """

    def __init__(
        self,
        url: str,
        name: Optional[str] = None,
        timeout: float = 10.0,
        fetcher: Optional[Callable[[str, float], str]] = None,
        region_filter: Optional[set] = None,
    ) -> None:
        self.url = url
        self.name = name or _host(url)
        self.timeout = timeout
        self._fetch = fetcher or _default_fetch
        self.region_filter = region_filter

    def fetch(self) -> List[Dict]:
        try:
            xml_text = self._fetch(self.url, self.timeout)
        except Exception as exc:  # network errors must not sink the pipeline
            log.warning("deals.rss.fetch_failed", url=self.url, error=str(exc))
            return []
        deals = parse_feed(xml_text, self.name)
        if self.region_filter:
            deals = [d for d in deals if d.get("region") in self.region_filter]
        log.info("deals.rss.loaded", source=self.name, count=len(deals))
        return deals


def _host(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return f"rss:{m.group(1)}" if m else "rss"


def rss_sources_from_feeds(feeds: List[str], **kw) -> List[RSSSource]:
    return [RSSSource(u, **kw) for u in feeds if u]
