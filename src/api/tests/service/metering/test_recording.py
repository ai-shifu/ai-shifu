from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.metering import UsageContext, record_llm_usage, record_tts_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

_BUILTIN_DEMO_SHIFU_BID = "demo-configured-1"


@pytest.fixture
def metering_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_record_llm_usage_persists(metering_app):
    with metering_app.app_context():
        context = UsageContext(
            user_bid="user-1",
            shifu_bid="shifu-1",
            usage_scene=BILL_USAGE_SCENE_PROD,
        )
        usage_bid = record_llm_usage(
            metering_app,
            context,
            provider="openai",
            model="gpt-test",
            is_stream=True,
            input=10,
            input_cache=4,
            output=20,
            total=30,
            latency_ms=123,
        )
        assert usage_bid
        record = BillUsageRecord.query.filter_by(usage_bid=usage_bid).first()
        assert record is not None
        assert record.usage_type == BILL_USAGE_TYPE_LLM
        assert record.input == 10
        assert record.input_cache == 4
        assert record.output == 20
        assert record.total == 30
        assert record.billable == 1


def test_record_llm_usage_enqueues_settlement_for_billable_root_usage(
    metering_app,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.append(usage_bid),
    )

    with metering_app.app_context():
        usage_bid = record_llm_usage(
            metering_app,
            UsageContext(
                user_bid="user-enqueue-1",
                shifu_bid="shifu-enqueue-1",
                usage_scene=BILL_USAGE_SCENE_PROD,
            ),
            provider="openai",
            model="gpt-test",
            is_stream=False,
            input=3,
            output=5,
            total=8,
        )

    assert captured == [usage_bid]


def test_record_tts_usage_preview_defaults_to_billable_on(metering_app):
    with metering_app.app_context():
        context = UsageContext(
            user_bid="user-2",
            shifu_bid="shifu-2",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )
        parent_usage_bid = generate_id(metering_app)
        segment_usage_bid = record_tts_usage(
            metering_app,
            context,
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=12,
            output=12,
            total=12,
            word_count=12,
            duration_ms=1500,
            latency_ms=50,
            record_level=1,
            parent_usage_bid=parent_usage_bid,
            segment_index=0,
        )
        assert segment_usage_bid

        parent_record_bid = record_tts_usage(
            metering_app,
            context,
            usage_bid=parent_usage_bid,
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=30,
            output=28,
            total=28,
            word_count=28,
            duration_ms=2000,
            record_level=0,
            segment_count=1,
        )
        assert parent_record_bid == parent_usage_bid

        parent_record = BillUsageRecord.query.filter_by(
            usage_bid=parent_usage_bid
        ).first()
        assert parent_record is not None
        assert parent_record.usage_type == BILL_USAGE_TYPE_TTS
        assert parent_record.billable == 1
        assert parent_record.record_level == 0
        assert parent_record.segment_count == 1


def test_record_tts_usage_only_enqueues_root_billable_record(
    metering_app,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.append(usage_bid),
    )

    with metering_app.app_context():
        context = UsageContext(
            user_bid="user-tts-enqueue-1",
            shifu_bid="shifu-tts-enqueue-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )
        parent_usage_bid = generate_id(metering_app)

        record_tts_usage(
            metering_app,
            context,
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=10,
            output=10,
            total=10,
            word_count=10,
            duration_ms=1000,
            record_level=1,
            parent_usage_bid=parent_usage_bid,
            segment_index=0,
        )
        record_tts_usage(
            metering_app,
            context,
            usage_bid=parent_usage_bid,
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=20,
            output=20,
            total=20,
            word_count=20,
            duration_ms=2000,
            record_level=0,
            segment_count=1,
        )

    assert captured == [parent_usage_bid]


def test_record_debug_usage_respects_explicit_non_billable_override(metering_app):
    with metering_app.app_context():
        context = UsageContext(
            user_bid="user-3",
            shifu_bid="shifu-3",
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        usage_bid = record_llm_usage(
            metering_app,
            context,
            provider="openai",
            model="gpt-test",
            is_stream=False,
            input=5,
            output=7,
            total=12,
        )
        assert usage_bid
        record = BillUsageRecord.query.filter_by(usage_bid=usage_bid).first()
        assert record is not None
        assert record.billable == 0


def test_record_llm_usage_skips_settlement_enqueue_for_non_billable_usage(
    metering_app,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.append(usage_bid),
    )

    with metering_app.app_context():
        record_llm_usage(
            metering_app,
            UsageContext(
                user_bid="user-override-1",
                shifu_bid="shifu-override-1",
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=0,
            ),
            provider="openai",
            model="gpt-test",
            is_stream=False,
            input=5,
            output=7,
            total=12,
        )

    assert captured == []


def test_record_llm_usage_marks_builtin_demo_course_non_billable(
    metering_app,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.append(usage_bid),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": (
            _BUILTIN_DEMO_SHIFU_BID if key == "DEMO_SHIFU_BID" else default
        ),
    )

    with metering_app.app_context():
        usage_bid = record_llm_usage(
            metering_app,
            UsageContext(
                user_bid="user-demo-llm-1",
                shifu_bid=_BUILTIN_DEMO_SHIFU_BID,
                usage_scene=BILL_USAGE_SCENE_PROD,
            ),
            provider="openai",
            model="gpt-test",
            is_stream=False,
            input=8,
            output=13,
            total=21,
        )
        record = BillUsageRecord.query.filter_by(usage_bid=usage_bid).first()

    assert record is not None
    assert record.billable == 0
    assert captured == []


def test_record_tts_usage_marks_builtin_demo_course_non_billable(
    metering_app,
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: captured.append(usage_bid),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": (
            _BUILTIN_DEMO_SHIFU_BID if key == "DEMO_SHIFU_BID" else default
        ),
    )

    with metering_app.app_context():
        usage_bid = record_tts_usage(
            metering_app,
            UsageContext(
                user_bid="user-demo-tts-1",
                shifu_bid=_BUILTIN_DEMO_SHIFU_BID,
                usage_scene=BILL_USAGE_SCENE_PREVIEW,
                audio_bid="audio-demo-1",
            ),
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=18,
            output=18,
            total=18,
            word_count=18,
            duration_ms=1200,
            record_level=0,
            segment_count=1,
        )
        record = BillUsageRecord.query.filter_by(usage_bid=usage_bid).first()

    assert record is not None
    assert record.billable == 0
    assert captured == []
