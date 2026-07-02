"""Circuit Breaker (Bl) — halt publishing on repeated failures to prevent bad
evolution loops.

Classic three-state breaker:

  CLOSED   -> normal operation; failures counted.
  OPEN     -> tripped after ``failure_threshold`` consecutive failures; calls
              are rejected fast for ``reset_seconds``.
  HALF_OPEN-> a single trial call is allowed; success closes, failure re-opens.

The breaker takes an injectable ``clock`` so it is fully deterministic under
test (no wall-clock sleeps).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Optional


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_seconds: float = 30.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._clock = clock or time.monotonic
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> BreakerState:
        # Lazily transition OPEN -> HALF_OPEN once the cooldown has elapsed.
        if self._state == BreakerState.OPEN and self._opened_at is not None:
            if self._clock() - self._opened_at >= self.reset_seconds:
                self._state = BreakerState.HALF_OPEN
        return self._state

    @property
    def failures(self) -> int:
        return self._failures

    def allows(self) -> bool:
        """True if a call may proceed right now."""
        return self.state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)

    def before_call(self) -> None:
        if not self.allows():
            raise CircuitOpenError(
                f"circuit open; {self._remaining():.1f}s until half-open"
            )

    def record_success(self) -> None:
        self._failures = 0
        self._state = BreakerState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        # A failure while HALF_OPEN immediately re-opens the breaker.
        if self.state == BreakerState.HALF_OPEN:
            self._trip()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = self._clock()

    def _remaining(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.reset_seconds - (self._clock() - self._opened_at))
