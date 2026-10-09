"""Behavioral contract for retake allowances and interrupted generation."""

import pytest
from flaskr.service.learn.retake_policy import (
    RetakeAllowance,
    RetakeRuleError,
    RetakeState,
    begin_attempt,
    settle_attempt,
    validate_limit,
)


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "2", [], {}, 2147483648])
def test_limit_rejects_ambiguous_or_unrepresentable_values(value: object) -> None:
    with pytest.raises(RetakeRuleError, match="invalid_limit"):
        validate_limit(value)


@pytest.mark.parametrize("value", [None, 0, 1, 2147483647])
def test_limit_accepts_unlimited_zero_and_nonnegative_integers(value: object) -> None:
    validate_limit(value)


def test_last_slot_is_occupied_before_generation_finishes() -> None:
    allowance = RetakeAllowance(limit=2, used=1, reserved=1)
    assert allowance.remaining == 0
    assert not allowance.allowed


def test_unlimited_preserves_observed_usage() -> None:
    allowance = RetakeAllowance(limit=None, used=50, reserved=1)
    assert allowance.remaining is None
    assert allowance.allowed
    assert allowance.used == 50


def test_changes_to_limit_do_not_reset_usage() -> None:
    assert RetakeAllowance(limit=5, used=2, reserved=0).remaining == 3
    assert RetakeAllowance(limit=1, used=2, reserved=0).remaining == 0
    assert RetakeAllowance(limit=3, used=2, reserved=0).remaining == 1


@pytest.mark.parametrize("count", [-1, True, 0.5])
def test_invalid_counts_are_not_silently_normalized(count: object) -> None:
    with pytest.raises(RetakeRuleError, match="invalid_count"):
        RetakeAllowance(limit=2, used=count, reserved=0)
    with pytest.raises(RetakeRuleError, match="invalid_count"):
        RetakeAllowance(limit=2, used=0, reserved=count)


def test_producer_cannot_start_the_same_attempt_twice() -> None:
    running = begin_attempt(RetakeState.RESERVED)
    assert running == RetakeState.RUNNING
    with pytest.raises(RetakeRuleError, match="attempt_not_reserved"):
        begin_attempt(running)


def test_durable_content_counts_even_if_transport_later_disconnects() -> None:
    assert (
        settle_attempt(
            RetakeState.RUNNING, has_durable_content=True, producer_stopped=False
        )
        == RetakeState.COMMITTED
    )


def test_failure_without_content_releases_only_after_producer_stops() -> None:
    with pytest.raises(RetakeRuleError, match="producer_still_running"):
        settle_attempt(
            RetakeState.RUNNING, has_durable_content=False, producer_stopped=False
        )
    assert (
        settle_attempt(
            RetakeState.RUNNING, has_durable_content=False, producer_stopped=True
        )
        == RetakeState.RELEASED
    )


def test_cancelled_reservation_does_not_consume_a_successful_attempt() -> None:
    assert (
        settle_attempt(
            RetakeState.RESERVED, has_durable_content=False, producer_stopped=True
        )
        == RetakeState.RELEASED
    )


@pytest.mark.parametrize(
    ("state", "content"), [(RetakeState.COMMITTED, True), (RetakeState.RELEASED, False)]
)
def test_terminal_retries_are_idempotent(state: RetakeState, content: bool) -> None:
    assert (
        settle_attempt(state, has_durable_content=content, producer_stopped=True)
        == state
    )


@pytest.mark.parametrize(
    ("state", "content"), [(RetakeState.COMMITTED, False), (RetakeState.RELEASED, True)]
)
def test_late_callbacks_cannot_reverse_a_terminal_outcome(
    state: RetakeState, content: bool
) -> None:
    with pytest.raises(RetakeRuleError, match="terminal_outcome_conflict"):
        settle_attempt(state, has_durable_content=content, producer_stopped=True)


def test_unstarted_attempt_cannot_be_charged() -> None:
    with pytest.raises(RetakeRuleError, match="attempt_not_running"):
        settle_attempt(
            RetakeState.RESERVED, has_durable_content=True, producer_stopped=True
        )
