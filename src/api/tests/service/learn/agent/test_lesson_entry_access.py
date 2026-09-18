"""Cover who is allowed to be taught by the 2.0 engine.

The 1.0 path gates a paid lesson inside its run context, which the agent path does not build. That
gate is reimplemented here rather than inherited, so it is covered directly: putting a paid course
on the allowlist must not hand its content to anyone signed in.
"""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL, UNIT_TYPE_VALUE_TRIAL

USER = "user-bid"


class _Shifu:
    def __init__(self, price: float) -> None:
        self.shifu_bid = "shifu-bid"
        self.price = price


class _Outline:
    def __init__(self, unit_type: int) -> None:
        self.type = unit_type


class _App:
    import logging

    logger = logging.getLogger("test_lesson_entry_access")


@pytest.fixture
def unpaid(monkeypatch: pytest.MonkeyPatch) -> None:
    """No successful order exists for this learner."""
    monkeypatch.setattr(lesson_entry, "_has_bought", lambda **_kwargs: False)


def _check(**kwargs: object) -> None:
    defaults = {
        "user_bid": USER,
        "shifu": _Shifu(price=99),
        "outline": _Outline(UNIT_TYPE_VALUE_NORMAL),
        "preview_mode": False,
    }
    lesson_entry._require_access(_App(), **{**defaults, **kwargs})


@pytest.mark.usefixtures("unpaid")
def test_an_unpaid_learner_is_refused_a_paid_lesson() -> None:
    """Without this, allowlisting a paid course would publish it to every signed-in user."""
    with pytest.raises(PaidError):
        _check()


@pytest.mark.usefixtures("unpaid")
def test_a_trial_lesson_stays_readable_before_buying() -> None:
    """Being readable without a purchase is what a trial lesson is for."""
    _check(outline=_Outline(UNIT_TYPE_VALUE_TRIAL))


@pytest.mark.usefixtures("unpaid")
def test_a_free_course_needs_no_purchase() -> None:
    _check(shifu=_Shifu(price=0))


@pytest.mark.usefixtures("unpaid")
def test_an_author_previewing_their_own_course_is_not_gated() -> None:
    _check(preview_mode=True)


def test_a_learner_who_bought_the_course_is_taught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lesson_entry, "_has_bought", lambda **_kwargs: True)
    _check()


@pytest.mark.usefixtures("unpaid")
def test_the_purchase_is_looked_up_for_the_course_that_owns_the_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lookup against the requested course rather than the outline's would gate the wrong one."""
    asked: list[dict] = []
    monkeypatch.setattr(
        lesson_entry,
        "_has_bought",
        lambda **kwargs: asked.append(kwargs) or True,
    )
    _check()
    assert asked == [{"user_bid": USER, "shifu_bid": "shifu-bid"}]
