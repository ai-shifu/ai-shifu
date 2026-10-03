"""Pure retake rules shared by persistence, HTTP validation and runtime settlement.

A reservation consumes availability, but is not a successful retake. Only durable
teaching content confirms an attempt. Transport retries must reuse its identity.
This module deliberately has no model, billing, UI or deployment side effects.
"""

from dataclasses import dataclass
from enum import StrEnum


class RetakeState(StrEnum):
    """Durable states of one learner-initiated retake."""

    RESERVED = "reserved"
    RUNNING = "running"
    COMMITTED = "committed"
    RELEASED = "released"


class RetakeRuleError(ValueError):
    """A stable reason the service can map to a localized API error."""


@dataclass(frozen=True)
class RetakeAllowance:
    """The balance of one learner and one lesson, not a course-wide pool."""

    limit: int | None
    used: int
    reserved: int

    def __post_init__(self) -> None:
        """Reject invalid persisted or submitted values, including booleans."""
        validate_limit(self.limit)
        for count in (self.used, self.reserved):
            if type(count) is not int or count < 0:
                reason = "invalid_count"
                raise RetakeRuleError(reason)

    @property
    def remaining(self) -> int | None:
        """Reservations occupy capacity until explicitly settled."""
        if self.limit is None:
            return None
        return max(0, self.limit - self.used - self.reserved)

    @property
    def allowed(self) -> bool:
        """A lowered limit never cancels existing attempts."""
        return self.remaining is None or self.remaining > 0


def validate_limit(value: object) -> None:
    """None is unlimited; zero forbids new attempts, not ongoing study."""
    if value is not None and (
        type(value) is not int or value < 0 or value > 2147483647
    ):
        reason = "invalid_limit"
        raise RetakeRuleError(reason)


def begin_attempt(state: RetakeState) -> RetakeState:
    """Exactly one producer can claim a reserved attempt under the DB lock."""
    if state != RetakeState.RESERVED:
        reason = "attempt_not_reserved"
        raise RetakeRuleError(reason)
    return RetakeState.RUNNING


def settle_attempt(
    state: RetakeState,
    *,
    has_durable_content: bool,
    producer_stopped: bool,
) -> RetakeState:
    """Never refund a live producer, or refund a partially delivered round.

    A retry of the same terminal transition is safe. A contradictory terminal
    transition is refused rather than rewriting charged usage or resurrecting an
    already released attempt. A timeout alone is not proof a producer stopped.
    """
    if state in (RetakeState.COMMITTED, RetakeState.RELEASED):
        expected = (
            RetakeState.COMMITTED if has_durable_content else RetakeState.RELEASED
        )
        if state != expected:
            reason = "terminal_outcome_conflict"
            raise RetakeRuleError(reason)
        return state
    if has_durable_content:
        if state != RetakeState.RUNNING:
            reason = "attempt_not_running"
            raise RetakeRuleError(reason)
        return RetakeState.COMMITTED
    if not producer_stopped:
        reason = "producer_still_running"
        raise RetakeRuleError(reason)
    return RetakeState.RELEASED
