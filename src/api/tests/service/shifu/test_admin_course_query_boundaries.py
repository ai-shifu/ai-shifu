"""Verify latest-course queries preserve visibility, activity, and draft history."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.shifu.admin_operations import courses_listing as listing
from flaskr.service.shifu.models import DraftShifu
from flaskr.util.datetime import now_utc


@pytest.fixture
def course_scope(app: object) -> Iterator[str]:
    with app.app_context():
        yield uuid.uuid4().hex
        db.session.rollback()


def _course(
    scope: str, bid: str, model: type = DraftShifu, **overrides: object
) -> object:
    now = now_utc()
    row = model(
        **{
            "shifu_bid": bid,
            "title": "Course",
            "created_user_bid": scope,
            "updated_user_bid": scope,
            "llm": "model",
            "tts_model": "voice-model",
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=1),
            "price": Decimal("12.34"),
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _filters(**overrides: object) -> dict:
    return {
        "shifu_bid": "",
        "course_name": "",
        "creator_bids": None,
        "start_time": None,
        "end_time": None,
        "updated_start_time": None,
        "updated_end_time": None,
        **overrides,
    }


def test_tts_fallback_preserves_latest_course_model_and_explicit_configuration(
    course_scope: str,
) -> None:
    bid = uuid.uuid4().hex
    _course(course_scope, bid, llm="fallback-model", tts_model="fallback-voice")
    latest = _course(course_scope, bid, llm="", tts_model="")
    result = listing._load_latest_shifus(DraftShifu, **_filters(shifu_bid=bid))
    assert result == [latest]
    assert latest.llm == ""
    assert latest.tts_model == "fallback-voice"
    explicit = SimpleNamespace(
        shifu_bid=bid, llm="explicit", tts_model="explicit-voice"
    )
    orphan = SimpleNamespace(shifu_bid="missing", llm="", tts_model="")
    listing._apply_latest_nonempty_model_fields(DraftShifu, [explicit, orphan])
    assert (explicit.llm, explicit.tts_model) == ("explicit", "explicit-voice")
    assert orphan.llm == ""
    listing._apply_latest_nonempty_model_fields(DraftShifu, [])
    listing._apply_latest_nonempty_model_fields(
        DraftShifu, [SimpleNamespace(shifu_bid="")]
    )


@pytest.mark.parametrize("loader", ["seeds", "lightweight"])
def test_latest_lightweight_seeds_recover_tts_without_changing_course_model_selection(
    course_scope: str,
    loader: str,
) -> None:
    bid = uuid.uuid4().hex
    _course(course_scope, bid, llm="saved-model", tts_model="saved-voice")
    latest = _course(course_scope, bid, llm="", tts_model="")
    seeds = (
        listing._load_latest_shifu_seeds(DraftShifu, **_filters(shifu_bid=bid))
        if loader == "seeds"
        else listing._load_latest_shifus(
            DraftShifu, **_filters(shifu_bid=bid), lightweight=True
        )
    )
    assert [(row.llm, row.tts_model) for row in seeds] == [("", "saved-voice")]
    assert (latest.llm, latest.tts_model) == ("", "")
    assert latest not in db.session.dirty
