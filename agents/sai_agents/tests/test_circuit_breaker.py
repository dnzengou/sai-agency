import pytest

from sai_agents.kafca.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitOpenError,
)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_trips_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, reset_seconds=10)
    assert cb.state is BreakerState.CLOSED
    for _ in range(3):
        cb.record_failure()
    assert cb.state is BreakerState.OPEN
    assert not cb.allows()
    with pytest.raises(CircuitOpenError):
        cb.before_call()


def test_half_open_then_close_on_success():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, reset_seconds=5, clock=clock)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is BreakerState.OPEN
    clock.advance(5)
    assert cb.state is BreakerState.HALF_OPEN
    assert cb.allows()
    cb.record_success()
    assert cb.state is BreakerState.CLOSED
    assert cb.failures == 0


def test_half_open_failure_reopens():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, reset_seconds=5, clock=clock)
    cb.record_failure()
    assert cb.state is BreakerState.OPEN
    clock.advance(5)
    assert cb.state is BreakerState.HALF_OPEN
    cb.record_failure()
    assert cb.state is BreakerState.OPEN


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failures == 0
    cb.record_failure()
    assert cb.state is BreakerState.CLOSED


def test_invalid_threshold():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
