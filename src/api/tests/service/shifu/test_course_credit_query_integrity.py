"""Protect course billing summaries from stale rows and cross-learner output."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import CreditLedgerEntry
from flaskr.service.common.models import AppError
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.admin_operations import courses_credit_usage as usage_service
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)


@pytest.fixture
def metering_scope(app: object) -> Iterator[dict]:
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
            "generated_block_bid": uuid.uuid4().hex,
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


def _element(scope: dict, block_bid: str, content: str, **overrides: object) -> None:
    db.session.add(
        LearnGeneratedElement(
            **{
                **scope,
                "generated_block_bid": block_bid,
                "element_bid": uuid.uuid4().hex,
                "role": "teacher",
                "event_type": "element",
                "is_final": 1,
                "is_renderable": 1,
                "status": 1,
                "content_text": content,
                **overrides,
            }
        )
    )
    db.session.flush()


def _block(scope: dict, block_bid: str, **overrides: object) -> None:
    db.session.add(
        LearnGeneratedBlock(
            **{
                **scope,
                "generated_block_bid": block_bid,
                "type": BLOCK_TYPE_MDCONTENT_VALUE,
                "status": 1,
                **overrides,
            }
        )
    )
    db.session.flush()


def _charge(row: BillUsageRecord, amount: str, **overrides: object) -> None:
    db.session.add(
        CreditLedgerEntry(
            **{
                "ledger_bid": uuid.uuid4().hex,
                "creator_bid": row.user_bid,
                "source_bid": row.usage_bid,
                "entry_type": CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                "source_type": CREDIT_SOURCE_TYPE_USAGE,
                "idempotency_key": uuid.uuid4().hex,
                "amount": Decimal(amount),
                **overrides,
            }
        )
    )
    db.session.flush()


@pytest.mark.parametrize("batch", [False, True])
def test_output_summaries_preserve_sequence_and_only_include_final_teacher_output(
    metering_scope: dict, batch: bool
) -> None:
    row = _usage(metering_scope)
    _element(metering_scope, row.generated_block_bid, " second ", sequence_number=2)
    _element(metering_scope, row.generated_block_bid, " first ", sequence_number=1)
    for excluded in [
        {"role": "student"},
        {"event_type": "debug"},
        {"is_final": 0},
        {"is_renderable": 0},
        {"deleted": 1},
        {"status": 0},
        {"user_bid": uuid.uuid4().hex},
        {"shifu_bid": uuid.uuid4().hex},
        {"outline_item_bid": uuid.uuid4().hex},
    ]:
        _element(metering_scope, row.generated_block_bid, "excluded", **excluded)
    _block(metering_scope, row.generated_block_bid, generated_content="legacy")
    if batch:
        assert usage_service._load_course_credit_usage_output_summary_map([row]) == {
            row.usage_bid: "first\nsecond"
        }
    else:
        assert usage_service._resolve_course_credit_usage_output_summary(row) == (
            "first\nsecond"
        )


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize(
    ("block_type", "content", "configuration", "expected"),
    [
        (BLOCK_TYPE_MDCONTENT_VALUE, " current content ", "", "current content"),
        (BLOCK_TYPE_MDINTERACTION_VALUE, "", " Pick a choice ", "Pick a choice"),
        (BLOCK_TYPE_MDCONTENT_VALUE, "", "not learner output", ""),
    ],
)
def test_output_summaries_fall_back_to_latest_active_legacy_block(
    metering_scope: dict,
    batch: bool,
    block_type: int,
    content: str,
    configuration: str,
    expected: str,
) -> None:
    row = _usage(metering_scope)
    _element(metering_scope, row.generated_block_bid, "   ")
    _block(
        metering_scope,
        row.generated_block_bid,
        type=block_type,
        generated_content=content,
        block_content_conf=configuration,
    )
    _block(
        metering_scope, row.generated_block_bid, generated_content="deleted", deleted=1
    )
    _block(
        metering_scope, row.generated_block_bid, generated_content="inactive", status=0
    )
    if batch:
        assert usage_service._load_course_credit_usage_output_summary_map([row]) == (
            {row.usage_bid: expected} if expected else {}
        )
    else:
        assert (
            usage_service._resolve_course_credit_usage_output_summary(row) == expected
        )


def test_batch_output_requires_exact_context_not_cross_product_of_requested_ids(
    metering_scope: dict,
) -> None:
    first = _usage(metering_scope)
    second_scope = {key: uuid.uuid4().hex for key in metering_scope}
    second = _usage(second_scope)
    _element(metering_scope, second.generated_block_bid, "cross-context element")
    _block(
        metering_scope,
        second.generated_block_bid,
        generated_content="cross-context block",
    )
    _block(second_scope, second.generated_block_bid, generated_content="older")
    _block(second_scope, second.generated_block_bid, generated_content="second output")
    _block(metering_scope, first.generated_block_bid, generated_content="first output")
    assert usage_service._load_course_credit_usage_output_summary_map(
        [first, second]
    ) == {
        first.usage_bid: "first output",
        second.usage_bid: "second output",
    }


@pytest.mark.parametrize("batch", [False, True])
def test_output_summary_caps_ordered_elements_and_handles_missing_block(
    metering_scope: dict, batch: bool
) -> None:
    row = _usage(metering_scope)
    for index in reversed(range(22)):
        _element(
            metering_scope, row.generated_block_bid, str(index), sequence_number=index
        )
    expected = "\n".join(str(index) for index in range(20))
    absent = _usage(metering_scope, generated_block_bid="")
    missing = _usage(metering_scope)
    if batch:
        assert usage_service._load_course_credit_usage_output_summary_map(
            [row, absent, missing]
        ) == {row.usage_bid: expected}
        assert (
            usage_service._load_course_credit_usage_output_summary_map([absent]) == {}
        )
    else:
        assert (
            usage_service._resolve_course_credit_usage_output_summary(row) == expected
        )
        assert usage_service._resolve_course_credit_usage_output_summary(absent) == ""
        assert usage_service._resolve_course_credit_usage_output_summary(missing) == ""


def test_usage_revision_queries_ignore_deleted_rows_and_scope_latest_parent_to_user(
    metering_scope: dict,
) -> None:
    old = _usage(metering_scope)
    latest = _usage(metering_scope, usage_bid=old.usage_bid, provider="latest")
    _usage(metering_scope, usage_bid=old.usage_bid, deleted=1)
    _usage(metering_scope, record_level=1)
    foreign = _usage({**metering_scope, "user_bid": uuid.uuid4().hex})
    result = usage_service._load_bill_usage_record_map(
        ["", old.usage_bid, f" {old.usage_bid} "]
    )
    assert result == {old.usage_bid: latest}
    assert usage_service._load_bill_usage_record_map(["", " "]) == {}
    subquery = usage_service._build_latest_bill_usage_record_subquery(
        user_bid=f" {metering_scope['user_bid']} ",
        usage_bids=[old.usage_bid, foreign.usage_bid],
    )
    assert db.session.query(subquery.c.usage_bid, subquery.c.max_id).all() == [
        (old.usage_bid, latest.id)
    ]
    empty = usage_service._build_latest_bill_usage_record_subquery(usage_bids=[" "])
    assert db.session.query(empty).all() == []


@pytest.mark.parametrize(
    ("scene", "expected_scene"),
    [
        (BILL_USAGE_SCENE_PROD, "learning"),
        (BILL_USAGE_SCENE_DEBUG, "debug"),
        (BILL_USAGE_SCENE_PREVIEW, "preview"),
    ],
)
def test_course_metering_query_only_counts_active_billable_consumption_for_requested_leaf(
    metering_scope: dict, scene: int, expected_scene: str
) -> None:
    included = _usage(metering_scope, usage_scene=scene)
    _charge(included, "-3.25")
    _charge(included, "-1.50")
    _charge(included, "-100", deleted=1)
    _charge(included, "-100", entry_type=999)
    _charge(included, "-100", source_type=999)
    for overrides in [
        {"billable": 0},
        {"status": 1},
        {"record_level": 1},
        {"deleted": 1},
        {"usage_scene": 999},
        {"shifu_bid": uuid.uuid4().hex},
        {"outline_item_bid": uuid.uuid4().hex},
    ]:
        excluded = _usage(metering_scope, **overrides)
        _charge(excluded, "-100")
    positive = _usage(metering_scope, usage_scene=scene)
    _charge(positive, "3")
    query = usage_service._build_operator_course_credit_usage_base_query(
        metering_scope["shifu_bid"],
        outline_item_bids=[metering_scope["outline_item_bid"]],
    )
    result = query.filter(
        usage_service._build_course_credit_usage_scene_filter(expected_scene)
    ).all()
    assert result == [(included, Decimal("-4.75"))]
    assert usage_service._resolve_course_credit_usage_scene(included) == expected_scene
    assert (
        usage_service._build_operator_course_credit_usage_base_query(
            metering_scope["shifu_bid"], outline_item_bids=[]
        ).all()
        == []
    )


@pytest.mark.parametrize(
    ("shifu_bid", "filters"),
    [
        ("", {}),
        ("course", {}),
        ("course", {"user_bid": "learner"}),
        (
            "course",
            {"user_bid": "learner", "outline_item_bid": "lesson", "mode": "invalid"},
        ),
        (
            "course",
            {
                "user_bid": "learner",
                "outline_item_bid": "lesson",
                "usage_scene": "invalid",
            },
        ),
    ],
)
def test_credit_detail_rejects_incomplete_or_invalid_filter_before_query(
    app: object, monkeypatch: pytest.MonkeyPatch, shifu_bid: str, filters: dict
) -> None:
    loader = Mock(side_effect=AssertionError("Validation must precede database lookup"))
    monkeypatch.setattr(usage_service, "_load_operator_course_outline_items", loader)
    with pytest.raises(AppError) as caught:
        usage_service.get_operator_course_credit_usage_details(
            app, shifu_bid=shifu_bid, page_index=1, page_size=10, filters=filters
        )
    assert caught.value.code == 2001
    loader.assert_not_called()


def test_model_labels_merge_current_and_legacy_provider_registries_once(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = Mock(
        return_value=[
            {"model": "shared", "display_name": "Current label"},
            {"model": "direct", "display_name": "Direct label", "provider": "First"},
        ]
    )
    monkeypatch.setattr(usage_service, "get_current_models", models)
    monkeypatch.setattr(
        usage_service,
        "PROVIDER_STATES",
        {
            "Second": SimpleNamespace(models=["shared", "unknown"]),
            "": SimpleNamespace(models=["shared"]),
        },
    )
    voice = Mock(
        return_value={
            "model_options": [
                {"provider": "Voice", "model": "main", "label": "Voice main"}
            ],
            "providers": [
                {
                    "name": "Legacy",
                    "models": [{"value": "old", "label": "Legacy voice"}],
                },
                {"name": "", "models": [{"value": "bad", "label": "Ignore"}]},
            ],
        }
    )
    monkeypatch.setattr(usage_service, "get_all_provider_configs", voice)
    resolver = usage_service._CourseCreditUsageModelLabelResolver(app)
    for provider, model, expected in [
        ("First", "direct", "Direct label"),
        ("Second", "shared", "Current label"),
    ]:
        assert (
            resolver.resolve(
                usage_type=BILL_USAGE_TYPE_LLM, provider=provider, model=model
            )
            == expected
        )
    for provider, model, expected in [
        ("Voice", "main", "Voice main"),
        ("Legacy", "old", "Legacy voice"),
    ]:
        assert (
            resolver.resolve(
                usage_type=BILL_USAGE_TYPE_TTS, provider=provider, model=model
            )
            == expected
        )
    assert resolver.resolve(usage_type=BILL_USAGE_TYPE_LLM, provider="", model="") == ""
    models.assert_called_once_with(app)
    voice.assert_called_once_with()


@pytest.mark.parametrize("usage_type", [BILL_USAGE_TYPE_LLM, BILL_USAGE_TYPE_TTS])
def test_model_label_registry_failure_is_cached_and_keeps_usage_readable(
    app: object, monkeypatch: pytest.MonkeyPatch, usage_type: int
) -> None:
    lookup = Mock(side_effect=RuntimeError("registry unavailable"))
    monkeypatch.setattr(usage_service, "get_current_models", lookup)
    monkeypatch.setattr(usage_service, "get_all_provider_configs", lookup)
    resolver = usage_service._CourseCreditUsageModelLabelResolver(app)
    for _ in range(2):
        assert (
            resolver.resolve(
                usage_type=usage_type,
                provider="provider",
                model="provider/doubao--seed-1-6-20260101",
            )
            == "Doubao-Seed-1.6"
        )
    lookup.assert_called_once()


def test_usage_dto_keeps_ledger_precision_and_group_identity_without_optional_context(
    metering_scope: dict,
) -> None:
    row = _usage(metering_scope, usage_scene=999)
    item = usage_service._build_operator_course_credit_usage_item(
        usage_row=row,
        ledger_amount=Decimal("-1.25"),
        user_map={},
        outline_context_map={},
    )
    assert item.consumed_credits == 1.25
    assert item.lesson_outline_item_bid == row.outline_item_bid
    assert item.group_key == row.usage_bid
    assert item.usage_scene == ""
    assert item.usage_mode == "learn"
    assert (
        usage_service._build_course_credit_usage_group_key(
            " progress ", " debug ", " ask ", row.usage_bid
        )
        == "progress:debug:ask"
    )
    assert (
        usage_service._build_course_credit_usage_group_key(
            " progress ", "", "", row.usage_bid
        )
        == "progress"
    )
    assert (
        usage_service._build_course_credit_usage_group_key(
            "", "debug", "learn", f" {row.usage_bid} "
        )
        == row.usage_bid
    )
    assert usage_service._format_course_credit_usage_model_label_fallback(" ") == ""
