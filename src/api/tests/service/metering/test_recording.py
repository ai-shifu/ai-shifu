import pytest

from flaskr.service.metering import UsageContext, record_llm_usage, record_tts_usage
from flaskr.service.metering.models import BillingUsageRecord
from flaskr.util.uuid import generate_id


@pytest.mark.usefixtures("app")
def test_record_llm_usage_persists(app):
    with app.app_context():
        context = UsageContext(
            user_bid="user-1",
            shifu_bid="shifu-1",
            usage_scene=2,
        )
        usage_bid = record_llm_usage(
            app,
            context,
            provider="openai",
            model="gpt-test",
            is_stream=True,
            input=10,
            output=20,
            total=30,
            latency_ms=123,
        )
        assert usage_bid
        record = BillingUsageRecord.query.filter_by(usage_bid=usage_bid).first()
        assert record is not None
        assert record.usage_type == 1
        assert record.input == 10
        assert record.output == 20
        assert record.total == 30
        assert record.billable == 1


@pytest.mark.usefixtures("app")
def test_record_tts_usage_preview_billable_off(app):
    with app.app_context():
        context = UsageContext(
            user_bid="user-2",
            shifu_bid="shifu-2",
            usage_scene=1,
        )
        parent_usage_bid = generate_id(app)
        segment_usage_bid = record_tts_usage(
            app,
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
            app,
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

        parent_record = BillingUsageRecord.query.filter_by(
            usage_bid=parent_usage_bid
        ).first()
        assert parent_record is not None
        assert parent_record.usage_type == 2
        assert parent_record.billable == 0
        assert parent_record.record_level == 0
        assert parent_record.segment_count == 1
