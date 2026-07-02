"""Blacklist (Bl) — reject unsafe / jailbreak-style inputs before they can
contaminate the evolution loop.

Mirrors the ``evolved-skill-opt`` safety patterns: pattern-match known
prompt-injection / jailbreak / exfiltration phrasing and refuse to publish an
event derived from such input. Fail closed on match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Pattern

# Default jailbreak / injection / exfiltration signatures. Case-insensitive.
_DEFAULT_PATTERNS: tuple[str, ...] = (
    r"ignore (all|any|previous|prior|above) (instructions|prompts|rules)",
    r"disregard (all|any|the) (above|previous|prior|system)",
    r"you are (now )?(dan|do anything now|jailbroken|unrestricted)",
    r"developer mode",
    r"reveal (your )?(system prompt|hidden|secret)",
    r"print (your )?(system prompt|instructions|api[_ ]?key)",
    r"exfiltrat",
    r"bypass (the )?(safety|guardrail|filter|restriction)",
    r"pretend (you are|to be) (an )?(unrestricted|evil|amoral)",
    r"(drop|delete|truncate)\s+table",
    r"rm\s+-rf\s+/",
    r";\s*shutdown",
)


@dataclass(frozen=True)
class BlacklistVerdict:
    blocked: bool
    reason: Optional[str] = None
    matched: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return not self.blocked


@dataclass
class Blacklist:
    """Compiles signatures once and screens arbitrary text."""

    extra_patterns: Iterable[str] = field(default_factory=tuple)
    _compiled: List[Pattern[str]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        patterns = list(_DEFAULT_PATTERNS) + list(self.extra_patterns or ())
        self._compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    def screen(self, text: object) -> BlacklistVerdict:
        """Return a verdict for a piece of text. Non-strings are coerced."""
        if text is None:
            return BlacklistVerdict(blocked=False)
        candidate = text if isinstance(text, str) else str(text)
        for rx in self._compiled:
            m = rx.search(candidate)
            if m:
                return BlacklistVerdict(
                    blocked=True,
                    reason="matched blacklist signature",
                    matched=rx.pattern,
                )
        return BlacklistVerdict(blocked=False)

    def screen_many(self, texts: Iterable[object]) -> BlacklistVerdict:
        for t in texts:
            verdict = self.screen(t)
            if verdict.blocked:
                return verdict
        return BlacklistVerdict(blocked=False)
