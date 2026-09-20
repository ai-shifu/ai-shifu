"""Verify refund recovery reads complete, attributable provider evidence."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import stripe as stripe_sdk
from flask import Flask
from flaskr.service.order.payment_providers.base import PaymentRefundRequest
from flaskr.service.order.payment_providers.stripe import StripeProvider
from flaskr.service.order.payment_providers.wechatpay import WechatPayProvider


def _request(**metadata: object) -> PaymentRefundRequest:
    return PaymentRefundRequest(
        order_bid="bill-order",
        amount=1000,
        metadata={
            "bill_order_bid": "bill-order",
            "creator_bid": "creator",
            "currency": "usd",
            "payment_amount": 1000,
            "payment_intent_id": "pi_paid",
            "charge_id": "ch_paid",
            "refund_operation_bid": "refund-operation",
            "idempotency_key": "refund:stable",
            **metadata,
        },
    )


def _refund(**overrides: object) -> dict:
    return {
        "object": "refund",
        "id": "re_existing",
        "amount": 1000,
        "currency": "usd",
        "payment_intent": "pi_paid",
        "charge": "ch_paid",
        "status": "succeeded",
        "metadata": {
            "order_bid": "bill-order",
            "bill_order_bid": "bill-order",
            "creator_bid": "creator",
            "refund_operation_bid": "refund-operation",
        },
        **overrides,
    }


def _page(*refunds: dict, more: bool = False) -> dict:
    return {"object": "list", "data": list(refunds), "has_more": more}


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    api = SimpleNamespace(Refund=Mock())
    options = {"api_key": "sk-scoped", "stripe_version": "2025-01-27.acacia"}
    monkeypatch.setattr(
        StripeProvider, "_client_options", lambda _self, _app: (api, options)
    )
    return SimpleNamespace(api=api, options=options, app=Flask(__name__))


@pytest.mark.parametrize(
    "status", ["pending", "requires_action", "succeeded", "failed", "canceled"]
)
def test_known_refund_is_retrieved_without_creating_or_losing_status(
    status: str, transport: SimpleNamespace
) -> None:
    request = _request(refund_reference_id="re_existing")
    request.amount = 250
    payload = _refund(amount=250, status=status)
    transport.api.Refund.retrieve.return_value = stripe_sdk.Refund.construct_from(
        payload, "sk-scoped"
    )

    result = StripeProvider().reconcile_refund(request=request, app=transport.app)

    assert result.provider_reference == "re_existing"
    assert result.status == status
    assert result.raw_response == payload
    transport.api.Refund.retrieve.assert_called_once_with(
        "re_existing", **transport.options
    )
    transport.api.Refund.list.assert_not_called()
    transport.api.Refund.create.assert_not_called()


def test_complete_pagination_finds_exact_operation_after_failed_historical_attempt(
    transport: SimpleNamespace,
) -> None:
    old = _refund(id="re_old", status="failed")
    old["metadata"]["refund_operation_bid"] = "older-operation"
    recovered = _refund(amount=250)
    request = _request()
    request.amount = 250
    transport.api.Refund.list.side_effect = [_page(old, more=True), _page(recovered)]

    result = StripeProvider().reconcile_refund(request=request, app=transport.app)

    assert result.raw_response == recovered
    assert transport.api.Refund.list.call_args_list == [
        call(payment_intent="pi_paid", limit=100, **transport.options),
        call(
            payment_intent="pi_paid",
            limit=100,
            starting_after="re_old",
            **transport.options,
        ),
    ]
    transport.api.Refund.create.assert_not_called()


def test_charge_only_empty_history_is_the_only_absence_result(
    transport: SimpleNamespace,
) -> None:
    request = _request(payment_intent_id="")
    transport.api.Refund.list.return_value = _page()

    assert StripeProvider().reconcile_refund(request=request, app=transport.app) is None
    transport.api.Refund.list.assert_called_once_with(
        charge="ch_paid", limit=100, **transport.options
    )
    transport.api.Refund.create.assert_not_called()


def test_single_full_legacy_refund_recovers_without_operation_metadata(
    transport: SimpleNamespace,
) -> None:
    payload = _refund()
    del payload["metadata"]["refund_operation_bid"]
    transport.api.Refund.list.return_value = _page(payload)

    result = StripeProvider().reconcile_refund(request=_request(), app=transport.app)

    assert result.provider_reference == payload["id"]
    assert result.status == "succeeded"
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize("count", [1, 2])
def test_unlinked_partial_refunds_are_ambiguous_even_when_amount_is_unique(
    count: int, transport: SimpleNamespace
) -> None:
    payload = _refund(amount=250)
    del payload["metadata"]["refund_operation_bid"]
    request = _request()
    request.amount = 250
    transport.api.Refund.list.return_value = _page(
        *[dict(payload, id=f"re_{index}") for index in range(count)]
    )

    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=request, app=transport.app)
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize("status", ["pending", "requires_action", "succeeded"])
def test_another_active_refund_prevents_automatic_adoption(
    status: str, transport: SimpleNamespace
) -> None:
    other = _refund(id="re_other", status=status)
    other["metadata"]["refund_operation_bid"] = "other-operation"
    transport.api.Refund.list.return_value = _page(_refund(), other)

    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", 999),
        ("amount", "1000"),
        ("amount", True),
        ("currency", "eur"),
        ("currency", None),
        ("payment_intent", "pi_other"),
        ("charge", "ch_other"),
        ("payment_intent", None),
        ("status", "unknown"),
        ("status", None),
        ("id", ""),
        ("metadata", {}),
        ("object", "payment_intent"),
    ],
)
def test_inconsistent_or_incomplete_provider_evidence_cannot_be_adopted(
    field: str, value: object, transport: SimpleNamespace
) -> None:
    transport.api.Refund.retrieve.return_value = _refund(**{field: value})
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(
            request=_request(refund_reference_id="re_existing"), app=transport.app
        )
    transport.api.Refund.create.assert_not_called()
    transport.api.Refund.list.assert_not_called()


@pytest.mark.parametrize(
    "field", ["order_bid", "bill_order_bid", "creator_bid", "refund_operation_bid"]
)
def test_conflicting_owner_or_operation_is_rejected(
    field: str, transport: SimpleNamespace
) -> None:
    payload = _refund()
    payload["metadata"][field] = "someone-else"
    transport.api.Refund.list.return_value = _page(payload)
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


def test_expanded_payment_references_preserve_identity(
    transport: SimpleNamespace,
) -> None:
    transport.api.Refund.retrieve.return_value = _refund(
        payment_intent={"id": "pi_paid"}, charge={"id": "ch_paid"}
    )
    result = StripeProvider().reconcile_refund(
        request=_request(refund_reference_id="re_existing"), app=transport.app
    )
    assert result.provider_reference == "re_existing"


@pytest.mark.parametrize(
    "pages",
    [
        [_page(more=True)],
        [_page(_refund(), more=True), _page(_refund())],
        [_page(_refund(), more=True), {"data": [], "has_more": "false"}],
        [{"data": [], "has_more": None}],
        [{"data": None, "has_more": False}],
        [_page({"id": ""}, more=True)],
    ],
)
def test_malformed_or_nonprogressing_pages_fail_closed(
    pages: list, transport: SimpleNamespace
) -> None:
    transport.api.Refund.list.side_effect = pages
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


def test_later_page_failure_does_not_return_an_early_matching_refund(
    transport: SimpleNamespace,
) -> None:
    error = RuntimeError("provider unavailable")
    transport.api.Refund.list.side_effect = [_page(_refund(), more=True), error]
    with pytest.raises(RuntimeError, match="provider unavailable") as raised:
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    assert raised.value is error
    transport.api.Refund.create.assert_not_called()


def test_known_refund_query_failure_does_not_fall_back_to_create(
    transport: SimpleNamespace,
) -> None:
    error = RuntimeError("refund not found in this account")
    transport.api.Refund.retrieve.side_effect = error
    with pytest.raises(RuntimeError, match="not found") as raised:
        StripeProvider().reconcile_refund(
            request=_request(refund_reference_id="re_existing"), app=transport.app
        )
    assert raised.value is error
    transport.api.Refund.list.assert_not_called()
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [{"payment_intent_id": "", "charge_id": ""}, {"currency": ""}, {"currency": "US"}],
)
def test_incomplete_query_target_fails_before_provider_io(
    overrides: dict, transport: SimpleNamespace
) -> None:
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(
            request=_request(**overrides), app=transport.app
        )
    transport.api.Refund.list.assert_not_called()
    transport.api.Refund.retrieve.assert_not_called()
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize("amount", [None, 0, -1, True, "1000"])
def test_reconciliation_requires_an_exact_positive_integer_amount(
    amount: object, transport: SimpleNamespace
) -> None:
    request = _request()
    request.amount = amount
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=request, app=transport.app)
    transport.api.Refund.list.assert_not_called()
    transport.api.Refund.retrieve.assert_not_called()


def test_create_keeps_operation_metadata_and_does_not_mutate_the_prepared_request(
    transport: SimpleNamespace,
) -> None:
    request = _request(idempotency_key="refund:stable")
    request.reason = "requested_by_customer"
    original = deepcopy(request.metadata)
    transport.api.Refund.create.return_value = stripe_sdk.Refund.construct_from(
        _refund(), "sk-scoped"
    )
    provider = StripeProvider()

    provider.refund_payment(request=request, app=transport.app)
    provider.refund_payment(request=request, app=transport.app)

    first, second = transport.api.Refund.create.call_args_list
    assert first == second
    assert first.kwargs["idempotency_key"] == "refund:stable"
    assert first.kwargs["metadata"]["refund_operation_bid"] == "refund-operation"
    assert first.kwargs["reason"] == "requested_by_customer"
    assert "reason" not in first.kwargs["metadata"]
    assert "idempotency_key" not in first.kwargs["metadata"]
    assert request.metadata == original


def test_unsupported_provider_does_not_turn_reconciliation_into_a_refund() -> None:
    with pytest.raises(NotImplementedError, match="reconciliation"):
        WechatPayProvider().reconcile_refund(request=_request(), app=Flask(__name__))


@pytest.mark.parametrize(
    "field",
    [
        "object",
        "id",
        "amount",
        "currency",
        "payment_intent",
        "charge",
        "status",
        "metadata",
    ],
)
@pytest.mark.parametrize("operation", ["create", "reconcile"])
def test_missing_financial_evidence_is_rejected_for_creation_and_reconciliation(
    field: str, operation: str, transport: SimpleNamespace
) -> None:
    payload = _refund()
    del payload[field]
    transport.api.Refund.create.return_value = payload
    transport.api.Refund.retrieve.return_value = payload
    provider = StripeProvider()
    request = _request(refund_reference_id="re_existing")
    method = (
        provider.refund_payment if operation == "create" else provider.reconcile_refund
    )

    with pytest.raises(RuntimeError):
        method(request=request, app=transport.app)
    if operation == "reconcile":
        transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize(
    "status", ["pending", "requires_action", "succeeded", "failed", "canceled"]
)
def test_new_operation_creation_preserves_every_known_refund_status(
    status: str, transport: SimpleNamespace
) -> None:
    transport.api.Refund.create.return_value = _refund(status=status)
    result = StripeProvider().refund_payment(request=_request(), app=transport.app)
    assert result.status == status
    assert result.provider_reference == "re_existing"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", 999),
        ("currency", "eur"),
        ("payment_intent", "pi_other"),
        ("charge", "ch_other"),
        ("status", "unknown"),
        ("id", ""),
    ],
)
def test_creation_rejects_contradictory_financial_response(
    field: str, value: object, transport: SimpleNamespace
) -> None:
    transport.api.Refund.create.return_value = _refund(**{field: value})
    with pytest.raises(RuntimeError):
        StripeProvider().refund_payment(request=_request(), app=transport.app)


@pytest.mark.parametrize(
    "field", ["refund_operation_bid", "creator_bid", "bill_order_bid", "order_bid"]
)
def test_creation_cannot_drop_or_change_operation_ownership(
    field: str, transport: SimpleNamespace
) -> None:
    payload = _refund()
    del payload["metadata"][field]
    transport.api.Refund.create.return_value = payload
    with pytest.raises(RuntimeError):
        StripeProvider().refund_payment(request=_request(), app=transport.app)


@pytest.mark.parametrize("value", [None, [], "not-json", 1])
def test_nonobject_provider_payload_is_not_recoverable(
    value: object, transport: SimpleNamespace
) -> None:
    transport.api.Refund.retrieve.return_value = value
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(
            request=_request(refund_reference_id="re_existing"), app=transport.app
        )
    transport.api.Refund.create.assert_not_called()


def test_explicit_refund_id_must_equal_the_returned_object_id(
    transport: SimpleNamespace,
) -> None:
    transport.api.Refund.retrieve.return_value = _refund(id="re_other")
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(
            request=_request(refund_reference_id="re_existing"), app=transport.app
        )
    transport.api.Refund.list.assert_not_called()


def test_multiple_failed_refunds_with_the_same_operation_are_still_ambiguous(
    transport: SimpleNamespace,
) -> None:
    transport.api.Refund.list.return_value = _page(
        _refund(id="re_first", status="failed"),
        _refund(id="re_second", status="canceled"),
    )
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


@pytest.mark.parametrize("payment_amount", [None, True, "1000", 999])
def test_legacy_full_refund_requires_the_original_payment_amount(
    payment_amount: object, transport: SimpleNamespace
) -> None:
    payload = _refund()
    del payload["metadata"]["refund_operation_bid"]
    transport.api.Refund.list.return_value = _page(payload)
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(
            request=_request(payment_amount=payment_amount), app=transport.app
        )
    transport.api.Refund.create.assert_not_called()


def test_remote_legacy_refund_cannot_be_selected_from_multiple_historical_refunds(
    transport: SimpleNamespace,
) -> None:
    first = _refund(status="failed", id="re_first")
    second = _refund()
    del first["metadata"]["refund_operation_bid"]
    del second["metadata"]["refund_operation_bid"]
    transport.api.Refund.list.return_value = _page(first, second)
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


def test_partial_refund_with_explicit_reference_can_recover_legacy_metadata(
    transport: SimpleNamespace,
) -> None:
    payload = _refund(amount=250)
    del payload["metadata"]["refund_operation_bid"]
    request = _request(refund_reference_id="re_existing")
    request.amount = 250
    transport.api.Refund.retrieve.return_value = payload
    result = StripeProvider().reconcile_refund(request=request, app=transport.app)
    assert result.provider_reference == "re_existing"
    transport.api.Refund.create.assert_not_called()


def test_page_without_list_identity_does_not_prove_empty_history(
    transport: SimpleNamespace,
) -> None:
    transport.api.Refund.list.return_value = {"data": [], "has_more": False}
    with pytest.raises(RuntimeError):
        StripeProvider().reconcile_refund(request=_request(), app=transport.app)
    transport.api.Refund.create.assert_not_called()


def test_query_credentials_are_captured_for_each_call_without_global_sdk_mutation(
    transport: SimpleNamespace,
) -> None:
    original_key = stripe_sdk.api_key
    transport.api.Refund.list.return_value = _page()
    provider = StripeProvider()
    provider.reconcile_refund(request=_request(), app=transport.app)
    transport.options["api_key"] = "sk-another-account"
    transport.options["stripe_version"] = "2024-12-18.acacia"
    provider.reconcile_refund(request=_request(), app=transport.app)
    assert transport.api.Refund.list.call_args_list == [
        call(
            payment_intent="pi_paid",
            limit=100,
            api_key="sk-scoped",
            stripe_version="2025-01-27.acacia",
        ),
        call(
            payment_intent="pi_paid",
            limit=100,
            api_key="sk-another-account",
            stripe_version="2024-12-18.acacia",
        ),
    ]
    assert stripe_sdk.api_key == original_key


@pytest.mark.parametrize("key", [None, "", "  ", 123])
def test_new_operation_cannot_be_sent_without_a_stable_idempotency_key(
    key: object, transport: SimpleNamespace
) -> None:
    request = _request(idempotency_key=key)
    transport.api.Refund.create.return_value = _refund()
    with pytest.raises(RuntimeError, match="idempotency"):
        StripeProvider().refund_payment(request=request, app=transport.app)
    transport.api.Refund.create.assert_not_called()
