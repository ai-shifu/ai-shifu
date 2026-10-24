"""Exercise admin credit summaries against real scoped usage and learner rows."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.learn.const import LEARN_STATUS_COMPLETED
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu import admin_user_credits as credit_service
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc


@pytest.fixture
def usage_scope(app: object) -> Iterator[dict]:
    with app.app_context():
        yield {
            "shifu_bid": uuid.uuid4().hex,
            "user_bid": uuid.uuid4().hex,
            "outline_item_bid": uuid.uuid4().hex,
        }
        db.session.rollback()


def _usage(scope: dict, **overrides: object) -> BillUsageRecord:
    row = BillUsageRecord(
        **{
            **scope,
            "usage_bid": uuid.uuid4().hex,
            "usage_type": BILL_USAGE_TYPE_LLM,
            "usage_scene": BILL_USAGE_SCENE_PROD,
            "billable": 1,
            "status": 0,
            "record_level": 0,
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _block(scope: dict, **overrides: object) -> LearnGeneratedBlock:
    row = LearnGeneratedBlock(
        **{
            **scope,
            "generated_block_bid": uuid.uuid4().hex,
            "type": BLOCK_TYPE_MDCONTENT_VALUE,
            "status": 1,
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _element(scope: dict, **overrides: object) -> LearnGeneratedElement:
    row = LearnGeneratedElement(
        **{
            **scope,
            "element_bid": uuid.uuid4().hex,
            "role": "teacher",
            "event_type": "element",
            "is_final": 1,
            "is_renderable": 1,
            "status": 1,
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _charge(usage: BillUsageRecord, amount: int) -> None:
    db.session.add(
        CreditLedgerEntry(
            ledger_bid=uuid.uuid4().hex,
            creator_bid=usage.user_bid,
            source_bid=usage.usage_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            idempotency_key=uuid.uuid4().hex,
            amount=Decimal(-amount),
        )
    )
    db.session.flush()


def test_wallet_summary_resolves_refund_order_category_and_keeps_locked_topups_visible(
    usage_scope: dict,
) -> None:
    now = now_utc()
    creator_bid = usage_scope["user_bid"]
    order_bid = uuid.uuid4().hex
    db.session.add(
        BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_TOPUP,
        )
    )
    for source_type, category, amount, expires, source_bid, metadata in [
        (
            CREDIT_SOURCE_TYPE_REFUND,
            0,
            7,
            now + timedelta(days=30),
            order_bid,
            {"bill_order_bid": order_bid},
        ),
        (
            CREDIT_SOURCE_TYPE_MANUAL,
            CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            3,
            now + timedelta(days=10),
            "",
            {},
        ),
        (
            CREDIT_SOURCE_TYPE_MANUAL,
            CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            2,
            now + timedelta(days=5),
            "",
            {},
        ),
    ]:
        db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid=uuid.uuid4().hex,
                creator_bid=creator_bid,
                wallet_bid=uuid.uuid4().hex,
                bucket_category=category,
                source_type=source_type,
                source_bid=source_bid,
                available_credits=amount,
                priority=10,
                effective_from=now - timedelta(days=1),
                effective_to=expires,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json=metadata,
            )
        )
    db.session.flush()
    summary = credit_service._load_operator_user_credit_summary_map([creator_bid])[
        creator_bid
    ]
    assert summary["topup_credits"] == 7
    assert summary["subscription_credits"] == 5
    assert summary["available_credits"] == 5
    assert summary["credits_expire_at"] == now + timedelta(days=5)
    assert summary["has_active_subscription"] is False


def test_subscription_without_product_retains_end_date_but_has_no_display_name(
    usage_scope: dict,
) -> None:
    now = now_utc()
    creator_bid = usage_scope["user_bid"]
    ends = now + timedelta(days=10)
    db.session.add(
        BillingSubscription(
            subscription_bid=uuid.uuid4().hex,
            creator_bid=creator_bid,
            product_bid="",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=ends,
        )
    )
    db.session.flush()
    assert (
        credit_service._load_active_subscription_product_display_name_i18n_key(
            creator_bid, as_of=now
        )
        == ""
    )
    assert credit_service._load_operator_user_credit_summary_map([creator_bid])[
        creator_bid
    ] == {
        "available_credits": 0,
        "subscription_credits": 0,
        "topup_credits": 0,
        "credits_expire_at": ends,
        "has_active_subscription": True,
    }


def test_credit_usage_keyword_limits_results_to_matching_account(
    usage_scope: dict,
) -> None:
    matching = _usage(usage_scope)
    _usage({**usage_scope, "user_bid": uuid.uuid4().hex})
    db.session.add(UserEntity(user_bid=matching.user_bid, nickname="Specific learner"))
    db.session.flush()
    result = credit_service._apply_course_credit_usage_filters(
        BillUsageRecord.query.filter(
            BillUsageRecord.shifu_bid == usage_scope["shifu_bid"]
        ),
        {"keyword": "Specific learner"},
    ).all()
    assert result == [matching]


def test_usage_context_survives_a_removed_course_without_leaking_other_course_titles(
    usage_scope: dict,
) -> None:
    usage = _usage(usage_scope, usage_scene=BILL_USAGE_SCENE_DEBUG)
    ledger = CreditLedgerEntry(
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
        source_type=CREDIT_SOURCE_TYPE_USAGE,
        source_bid=usage.usage_bid,
    )
    result = credit_service._load_operator_user_credit_usage_context_map([ledger])
    assert result[usage.usage_bid]["course_bid"] == usage_scope["shifu_bid"]
    assert result[usage.usage_bid]["course_name"] == ""
    assert result[usage.usage_bid]["usage_scene"] == "debug"


def test_empty_usage_identifiers_do_not_run_unscoped_queries() -> None:
    assert credit_service._load_active_subscription_end_map([], as_of=now_utc()) == {}
    assert credit_service._load_operator_user_credit_summary_map([" ", ""]) == {}
    assert credit_service._load_operator_user_credit_usage_main_row(" ") is None
    assert credit_service._load_operator_user_credit_usage_segment_rows("") == []
    assert credit_service._load_generated_block_content_map([""]) == {}


def test_output_summaries_preserve_element_order_cap_and_full_learner_context(
    usage_scope: dict,
) -> None:
    block_bid = uuid.uuid4().hex
    row = _usage(usage_scope, generated_block_bid=block_bid)
    for index in reversed(range(22)):
        _element(
            usage_scope,
            generated_block_bid=block_bid,
            sequence_number=index,
            content_text=f" Segment {index} ",
        )
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        sequence_number=-1,
        content_text="Learner input must not leak",
        role="student",
    )
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        sequence_number=-2,
        content_text="Unfinished output",
        is_final=0,
    )
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        user_bid="another-learner",
        sequence_number=-3,
        content_text="Another learner output",
    )
    expected = "\n".join(f"Segment {index}" for index in range(20))
    assert credit_service._resolve_course_credit_usage_output_summary(row) == expected
    assert credit_service._load_course_credit_usage_output_summary_map([row]) == {
        row.usage_bid: expected
    }


def test_output_summary_falls_back_to_latest_legacy_block_or_interaction(
    usage_scope: dict,
) -> None:
    block = _block(usage_scope, generated_content="Old content")
    row = _usage(usage_scope, generated_block_bid=block.generated_block_bid)
    _block(
        usage_scope,
        generated_block_bid=block.generated_block_bid,
        generated_content=" New content ",
    )
    interaction = _block(
        usage_scope,
        type=BLOCK_TYPE_MDINTERACTION_VALUE,
        block_content_conf=" Choose an option ",
    )
    interaction_usage = _usage(
        usage_scope, generated_block_bid=interaction.generated_block_bid
    )
    missing = _usage(usage_scope, generated_block_bid="missing-block")
    assert (
        credit_service._resolve_course_credit_usage_output_summary(row) == "New content"
    )
    assert (
        credit_service._resolve_course_credit_usage_output_summary(interaction_usage)
        == "Choose an option"
    )
    assert credit_service._resolve_course_credit_usage_output_summary(missing) == ""
    assert credit_service._load_course_credit_usage_output_summary_map(
        [row, interaction_usage, missing]
    ) == {row.usage_bid: "New content", interaction_usage.usage_bid: "Choose an option"}
    assert credit_service._load_course_credit_usage_output_summary_map([]) == {}
    assert (
        credit_service._load_course_credit_usage_output_summary_map(
            [_usage(usage_scope)]
        )
        == {}
    )


def test_batch_summary_rejects_cross_product_context_matches(usage_scope: dict) -> None:
    first_block, second_block = uuid.uuid4().hex, uuid.uuid4().hex
    first = _usage(usage_scope, generated_block_bid=first_block)
    second = _usage(
        usage_scope,
        generated_block_bid=second_block,
        user_bid="second-learner",
        outline_item_bid="second-outline",
    )
    _element(
        usage_scope,
        generated_block_bid=first_block,
        user_bid="second-learner",
        content_text="Mixed context must not leak",
    )
    _block(
        usage_scope,
        generated_block_bid=second_block,
        user_bid="second-learner",
        outline_item_bid="second-outline",
        generated_content="Correct second output",
    )
    assert credit_service._load_course_credit_usage_output_summary_map(
        [first, second]
    ) == {second.usage_bid: "Correct second output"}


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("ask", {"ask", "preview-ask"}),
        ("learn", {"learn", "empty"}),
        ("listen", {"listen"}),
        ("invalid", {"ask", "preview-ask", "learn", "empty", "listen"}),
    ],
)
def test_usage_mode_filters_classify_provider_requests_in_database(
    usage_scope: dict, mode: str, expected: set[str]
) -> None:
    definitions = [
        ("ask", BILL_USAGE_TYPE_LLM, {"generation_name": "lesson_ask/request"}),
        (
            "preview-ask",
            BILL_USAGE_TYPE_LLM,
            {"generation_name": "lesson_preview_ask/request"},
        ),
        ("learn", BILL_USAGE_TYPE_LLM, {"generation_name": "lesson/run"}),
        ("empty", BILL_USAGE_TYPE_LLM, {}),
        ("listen", BILL_USAGE_TYPE_TTS, {"generation_name": "lesson_ask/request"}),
    ]
    for name, usage_type, extra in definitions:
        _usage(usage_scope, usage_bid=name, usage_type=usage_type, extra=extra)
    query = BillUsageRecord.query.filter_by(shifu_bid=usage_scope["shifu_bid"])
    result = credit_service._apply_course_credit_usage_filters(query, {"mode": mode})
    assert {row.usage_bid for row in result.all()} == expected


@pytest.mark.parametrize(
    ("scene", "scene_id"),
    [
        ("learning", BILL_USAGE_SCENE_PROD),
        ("preview", BILL_USAGE_SCENE_PREVIEW),
        ("debug", BILL_USAGE_SCENE_DEBUG),
    ],
)
def test_usage_scene_and_time_filters_bound_the_selected_window(
    usage_scope: dict, scene: str, scene_id: int
) -> None:
    now = now_utc()
    target = _usage(usage_scope, usage_scene=scene_id, created_at=now)
    _usage(usage_scope, usage_scene=scene_id, created_at=now - timedelta(days=3))
    _usage(usage_scope, usage_scene=0, created_at=now)
    query = BillUsageRecord.query.filter_by(shifu_bid=usage_scope["shifu_bid"])
    result = credit_service._apply_course_credit_usage_filters(
        query,
        {
            "usage_scene": scene,
            "start_time": now - timedelta(days=1),
            "end_time": now + timedelta(seconds=1),
        },
    )
    assert [row.usage_bid for row in result.all()] == [target.usage_bid]


def test_course_credit_metrics_count_only_charged_leaf_usages_and_current_completions(
    usage_scope: dict,
) -> None:
    now = now_utc()
    first = _usage(usage_scope, user_bid="completed-user", outline_item_bid="leaf-one")
    second = _usage(usage_scope, user_bid="completed-user", outline_item_bid="leaf-two")
    incomplete = _usage(
        usage_scope, user_bid="incomplete-user", outline_item_bid="leaf-one"
    )
    outside = _usage(
        usage_scope, user_bid="outside-user", outline_item_bid="outside-leaf"
    )
    for row, amount in [(first, 3), (second, 5), (incomplete, 4), (outside, 100)]:
        _charge(row, amount)
    for user_bid in ["completed-user", "incomplete-user"]:
        for outline in ["leaf-one", "leaf-two"]:
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex,
                    shifu_bid=usage_scope["shifu_bid"],
                    user_bid=user_bid,
                    outline_item_bid=outline,
                    status=LEARN_STATUS_COMPLETED,
                    updated_at=now - timedelta(seconds=1),
                )
            )
    db.session.add(
        LearnProgressRecord(
            progress_record_bid=uuid.uuid4().hex,
            shifu_bid=usage_scope["shifu_bid"],
            user_bid="incomplete-user",
            outline_item_bid="leaf-two",
            status=602,
            updated_at=now,
        )
    )
    db.session.flush()
    assert credit_service._build_operator_course_credit_metrics(
        usage_scope["shifu_bid"], ["leaf-one", "leaf-two"]
    ) == {
        "credit_consumed_total": 12,
        "credit_usage_count": 3,
        "credit_user_count": 2,
        "completed_credit_user_count": 1,
        "completed_user_avg_credits": 8,
    }
    empty = credit_service._build_operator_course_credit_metrics(
        usage_scope["shifu_bid"], []
    )
    assert empty == {
        "credit_consumed_total": 0,
        "credit_usage_count": 0,
        "credit_user_count": 0,
        "completed_credit_user_count": 0,
        "completed_user_avg_credits": None,
    }


def test_usage_dtos_preserve_caller_overrides_and_nonnegative_counts(
    usage_scope: dict,
) -> None:
    row = _usage(
        usage_scope,
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        provider="provider",
        model="model",
        input=7,
        output=11,
        word_count=12,
        duration_ms=1000,
        segment_count=2,
    )
    item = credit_service._build_operator_course_credit_usage_item(
        usage_row=row,
        ledger_amount=-3,
        user_map={row.user_bid: {"nickname": "Teacher"}},
        outline_context_map={},
        provider="override",
        model="override-model",
        consumed_credits=Decimal("2.5"),
        usage_count=0,
        model_variant_count=-1,
    )
    assert item.provider == "override"
    assert item.model == "override-model"
    assert item.usage_count == 1
    assert item.model_variant_count == 0
    assert item.consumed_credits == 2.5
    assert item.usage_scene == "debug"
    detail = credit_service._build_operator_course_credit_usage_detail_item(
        row, -3, output_summary="Explicit output"
    )
    assert detail.consumed_credits == 3
    assert detail.input_tokens == 7
    assert detail.output_tokens == 11
    assert detail.output_summary == "Explicit output"


def test_listen_content_mapping_handles_invalid_segments_and_fallback_order(
    usage_scope: dict,
) -> None:
    block_bid = uuid.uuid4().hex
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        progress_record_bid="progress",
        is_speakable=1,
        content_text="First",
        sequence_number=0,
        audio_segments='[{"segment_index": 3}, null, {"segment_index": "invalid"}]',
    )
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        progress_record_bid="progress",
        is_speakable=1,
        content_text="Second",
        sequence_number=1,
        audio_segments="broken-json",
    )
    _element(
        usage_scope,
        generated_block_bid=block_bid,
        progress_record_bid="progress",
        is_speakable=1,
        content_text=" ",
        sequence_number=2,
    )
    assert credit_service._load_listen_segment_content_map(
        progress_record_bid="progress", generated_block_bid=block_bid
    ) == {3: "First", 0: "Second"}
    assert (
        credit_service._load_listen_segment_content_map(
            progress_record_bid="", generated_block_bid=""
        )
        == {}
    )
