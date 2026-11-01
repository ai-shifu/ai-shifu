"""Protect the operator ledger's display, filtering, and allocation contracts."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import CreditLedgerEntry
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu import admin_user_credits as credit_service
from flaskr.service.shifu.admin_operations import (
    courses_credit_usage as course_usage_service,
)


@pytest.mark.parametrize(
    ("entry_type", "source_type", "amount", "metadata", "display", "source"),
    [
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            10,
            {"checkout_type": " TRIAL_BOOTSTRAP "},
            "trial_subscription_grant",
            "trial_subscription",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            10,
            {},
            "subscription_grant",
            "subscription",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_TOPUP,
            10,
            {},
            "topup_grant",
            "topup",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_GIFT,
            10,
            {},
            "gift_grant",
            "gift",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_MANUAL,
            10,
            {"grant_type": "manual_grant", "grant_source": "reward"},
            "manual_grant",
            "reward",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_MANUAL,
            0,
            {"grant_source": "unexpected"},
            "manual_credit",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CREDIT_SOURCE_TYPE_MANUAL,
            -10,
            {},
            "manual_debit",
            "manual",
        ),
        (CREDIT_LEDGER_ENTRY_TYPE_GRANT, -1, 10, {}, "grant", "manual"),
        (
            CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CREDIT_SOURCE_TYPE_USAGE,
            -10,
            {"usage_scene": BILL_USAGE_SCENE_PREVIEW},
            "preview_consume",
            "preview",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CREDIT_SOURCE_TYPE_USAGE,
            -10,
            {"usage_scene": BILL_USAGE_SCENE_DEBUG},
            "debug_consume",
            "debug",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CREDIT_SOURCE_TYPE_USAGE,
            -10,
            {"usage_scene": str(BILL_USAGE_SCENE_PROD)},
            "learning_consume",
            "learning",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CREDIT_SOURCE_TYPE_USAGE,
            -10,
            {"usage_scene": "malformed"},
            "consume",
            "usage",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CREDIT_SOURCE_TYPE_MANUAL,
            -10,
            {},
            "consume",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            CREDIT_SOURCE_TYPE_MANUAL,
            10,
            {},
            "manual_credit",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            CREDIT_SOURCE_TYPE_MANUAL,
            -10,
            {},
            "manual_debit",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            CREDIT_SOURCE_TYPE_MANUAL,
            0,
            {},
            "adjustment",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            -10,
            {},
            "subscription_expire",
            "subscription",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            CREDIT_SOURCE_TYPE_TOPUP,
            -10,
            {},
            "topup_expire",
            "topup",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            CREDIT_SOURCE_TYPE_GIFT,
            -10,
            {},
            "gift_expire",
            "gift",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            CREDIT_SOURCE_TYPE_MANUAL,
            -10,
            {},
            "expire",
            "manual",
        ),
        (
            CREDIT_LEDGER_ENTRY_TYPE_REFUND,
            CREDIT_SOURCE_TYPE_REFUND,
            10,
            {},
            "refund_return",
            "refund",
        ),
        (-1, -1, 0, {}, "grant", "manual"),
    ],
)
def test_ledger_display_distinguishes_grants_consumption_expiration_and_adjustments(
    entry_type: int,
    source_type: int,
    amount: int,
    metadata: dict,
    display: str,
    source: str,
) -> None:
    row = CreditLedgerEntry(
        ledger_bid="ledger",
        entry_type=entry_type,
        source_type=source_type,
        amount=Decimal(amount),
        balance_after=Decimal("12.34"),
        metadata_json=metadata,
    )
    result = credit_service._build_operator_user_credit_ledger_item(row)
    assert result.display_entry_type == display
    assert result.display_source_type == source
    assert Decimal(result.amount) == Decimal(amount)
    assert Decimal(result.balance_after) == Decimal("12.34")


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"checkout_type": "subscription_renewal"}, "subscription_renewal"),
        ({"checkout_type": "subscription"}, "subscription_purchase"),
        ({"checkout_type": "topup"}, "topup_purchase"),
        ({"checkout_type": "admin_manual_plan_grant"}, "admin_manual_plan_grant"),
        ({"checkout_type": "manual_grant"}, "manual_grant"),
        ({"reason": "subscription_cycle_transition"}, "subscription_cycle_transition"),
        ({"refund_return": True}, "refund_return"),
        ({"note": "Operator supplied note", "checkout_type": "topup"}, ""),
    ],
)
def test_ledger_note_codes_preserve_checkout_reason_and_explicit_note_precedence(
    metadata: dict,
    expected: str,
) -> None:
    row = CreditLedgerEntry(
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        amount=1,
    )
    assert (
        credit_service._resolve_operator_credit_note_code(row, metadata=metadata)
        == expected
    )


@pytest.mark.parametrize(
    ("service", "resolver", "value", "expected"),
    [
        (
            credit_service,
            "_resolve_course_credit_usage_scene_filter",
            " PREVIEW ",
            "preview",
        ),
        (
            credit_service,
            "_resolve_course_credit_usage_scene_filter",
            "unsupported",
            "",
        ),
        (course_usage_service, "_resolve_course_credit_usage_view", "", "grouped"),
        (
            course_usage_service,
            "_resolve_course_credit_usage_view",
            " GROUPED ",
            "grouped",
        ),
        (course_usage_service, "_resolve_course_credit_usage_view", " RAW ", "raw"),
        (course_usage_service, "_resolve_course_credit_usage_view", "unsupported", ""),
        (
            credit_service,
            "_resolve_operator_user_credit_type_filter",
            " GRANT ",
            "grant",
        ),
        (credit_service, "_resolve_operator_user_credit_type_filter", "", "all"),
        (
            credit_service,
            "_resolve_operator_user_credit_type_filter",
            "unsupported",
            "",
        ),
        (
            credit_service,
            "_resolve_operator_user_credit_grant_source_filter",
            " TRIAL_SUBSCRIPTION ",
            "trial_subscription",
        ),
        (
            credit_service,
            "_resolve_operator_user_credit_grant_source_filter",
            "",
            "all",
        ),
        (
            credit_service,
            "_resolve_operator_user_credit_grant_source_filter",
            "unsupported",
            "",
        ),
    ],
)
def test_credit_filter_normalization_rejects_unknown_values(
    service: object,
    resolver: str,
    value: str,
    expected: str,
) -> None:
    assert getattr(service, resolver)(value) == expected


def test_usage_group_keys_separate_scenes_and_modes_with_a_stable_ungrouped_fallback() -> (
    None
):
    build = course_usage_service._build_course_credit_usage_group_key
    assert (
        build(" progress ", " learning ", " ask ", "usage") == "progress:learning:ask"
    )
    assert build("progress", "preview", "ask", "usage") == "progress:preview:ask"
    assert build("progress", "", "", "usage") == "progress"
    assert build("", "learning", "ask", " usage ") == "usage"
    assert (
        course_usage_service._build_course_credit_usage_model_display(
            " provider ", " model "
        )
        == "provider / model"
    )
    assert (
        course_usage_service._build_course_credit_usage_model_display("", " model ")
        == "model"
    )
    assert (
        course_usage_service._build_course_credit_usage_model_display(" provider ", "")
        == "provider"
    )


def test_credit_allocation_conserves_total_despite_fractional_rounding_and_negative_units() -> (
    None
):
    rows = [
        SimpleNamespace(usage_bid=str(i), total=units)
        for i, units in enumerate([-5, 1, 1, 1])
    ]
    result = credit_service._allocate_usage_detail_credits(
        rows=rows,
        total_consumed_credits=Decimal("1.000000"),
    )
    assert result["0"] == 0
    assert sum(result.values()) == Decimal("1.000000")
    assert abs(result["1"] - result["3"]) <= Decimal("0.01")
    zero_rows = [
        SimpleNamespace(usage_bid="first", total=0),
        SimpleNamespace(usage_bid="second", total=-1),
    ]
    assert credit_service._allocate_usage_detail_credits(
        rows=zero_rows,
        total_consumed_credits=Decimal(3),
    ) == {"first": Decimal(3)}


def test_usage_detail_prefers_recorded_segment_text_over_later_rendered_content() -> (
    None
):
    row = SimpleNamespace(extra={"segment_text": " recorded ", "text": "second choice"})
    assert (
        credit_service._resolve_usage_detail_item_content(
            row,
            block_content_map={},
            listen_content_map={},
            fallback_content="fallback",
        )
        == "recorded"
    )


@pytest.mark.parametrize(
    ("scene", "expected"),
    [
        (BILL_USAGE_SCENE_PROD, "learning"),
        (BILL_USAGE_SCENE_PREVIEW, "preview"),
        (0, ""),
    ],
)
def test_usage_dto_derives_scene_and_consumed_amount_from_the_record(
    scene: int,
    expected: str,
) -> None:
    row = BillUsageRecord(usage_bid="usage", usage_scene=scene)
    result = course_usage_service._build_operator_course_credit_usage_item(
        usage_row=row,
        ledger_amount=Decimal("-3.25"),
        user_map={},
        outline_context_map={},
    )
    assert result.usage_scene == expected
    assert result.consumed_credits == 3.25
    assert result.group_key == "usage"
    assert credit_service._resolve_operator_user_credit_usage_scene(row) == expected


@pytest.mark.parametrize("amount", [Decimal(0), Decimal(-1)])
def test_credit_allocation_does_not_fabricate_charges_for_zero_or_negative_totals(
    amount: Decimal,
) -> None:
    assert (
        credit_service._allocate_usage_detail_credits(
            rows=[SimpleNamespace(usage_bid="usage", total=10)],
            total_consumed_credits=amount,
        )
        == {}
    )
