"""Project existing provider tables into stable learner attempt identities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.service.common.native_payment_status import (
    extract_native_trade_status,
    native_snapshot_status,
)

from .learner_payments import _stringify_payload
from .models import PingxxOrder, StripeOrder
from .payment_providers import historical_payment_definition
from .payment_providers.normalization import legacy_native_amount, native_facts
from .raw_snapshots import (
    _parse_json_payload,
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_bid_attr,
    native_snapshot_model,
    should_update_native_snapshot_status,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Query

    from .payment_providers.base import PaymentNotificationResult, PaymentRefundResult
    from .payment_providers.contracts import PaymentFacts


@dataclass(frozen=True, slots=True)
class SnapshotSchema:
    """Compatibility fields belong to storage, not purchase/refund rules."""

    attempt_attribute: str
    reference_attributes: tuple[str, ...]
    reference_types: tuple[str, ...]
    refundable_payload_attribute: str
    pending_statuses: tuple[int, ...] = (0,)


_SCHEMAS = {
    "stripe": SnapshotSchema(
        "stripe_order_bid",
        ("checkout_session_id", "payment_intent_id"),
        ("checkout_session", "payment_intent"),
        "payment_intent_object",
        (0, 4),
    ),
    "pingxx": SnapshotSchema(
        "pingxx_order_bid", ("charge_id",), ("charge",), "charge_object"
    ),
}

# Preserve the old native close aliases; new integrations use their declared
# close reference type, independently from query and renewal discriminators.
_LEGACY_NATIVE_CLOSE_REFERENCE_TYPES = {"alipay": "trade", "wechatpay": "trade"}


def _query_and_schema(provider: str) -> tuple[Query, type, SnapshotSchema]:
    definition = historical_payment_definition(provider)
    kind = definition.snapshot_kind
    if kind == "stripe":
        return legacy_stripe_snapshot_query(), StripeOrder, _SCHEMAS[kind]
    if kind == "pingxx":
        return legacy_pingxx_snapshot_query(), PingxxOrder, _SCHEMAS[kind]
    schema = SnapshotSchema(
        native_snapshot_bid_attr(provider),
        ("provider_attempt_id",),
        (
            definition.close_reference_type
            or _LEGACY_NATIVE_CLOSE_REFERENCE_TYPES.get(
                provider, definition.operation_reference_type("close")
            ),
        ),
        "raw_response",
    )
    return (
        legacy_native_snapshot_query(provider),
        native_snapshot_model(provider),
        schema,
    )


@dataclass(slots=True)
class PaymentAttempt:
    """A storage projection preserving the original table and immutable identity."""

    record: object
    schema: SnapshotSchema

    @property
    def attempt_bid(self) -> str:
        """Return the original local attempt key used by operation idempotency."""
        return str(getattr(self.record, self.schema.attempt_attribute) or "")

    @property
    def amount(self) -> int:
        """Return the stored minor-unit amount."""
        return int(self.record.amount or 0)

    @property
    def status(self) -> int:
        """Return the existing snapshot status."""
        return int(self.record.status or 0)

    @status.setter
    def status(self, value: int) -> None:
        self.record.status = value

    @property
    def metadata(self) -> dict:
        """Read old JSON text and normalized dictionary snapshots."""
        raw = getattr(self.record, "metadata_json", None)
        if isinstance(raw, dict):
            return dict(raw)
        try:
            value = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @metadata.setter
    def metadata(self, value: dict) -> None:
        self.record.metadata_json = json.dumps(value)

    def refund_metadata(self, *, order_bid: str, idempotency_key: str) -> dict:
        """Translate the persisted payment references for the owning refund adapter."""
        metadata = {"order_bid": order_bid, "idempotency_key": idempotency_key}
        if hasattr(self.record, "payment_intent_id"):
            metadata.update(
                payment_intent_id=self.record.payment_intent_id,
                charge_id=self.record.latest_charge_id,
            )
        else:
            metadata["provider_reference"] = str(
                getattr(self.record, self.schema.reference_attributes[0]) or ""
            )
        return metadata

    def persist_refund(self, result: PaymentRefundResult) -> None:
        """Store the original refund payload without deciding purchase state."""
        setattr(
            self.record,
            self.schema.refundable_payload_attribute,
            _stringify_payload(result.raw_response),
        )
        if hasattr(self.record, "failure_code") and result.status.lower() not in {
            "succeeded",
            "pending",
            "requires_action",
        }:
            self.record.failure_code = result.status or self.record.failure_code

    @property
    def reference(self) -> tuple[str, str]:
        """Return a close/query reference with its protocol-owned reference type."""
        for attribute, reference_type in zip(
            self.schema.reference_attributes, self.schema.reference_types, strict=True
        ):
            value = str(getattr(self.record, attribute) or "")
            if value:
                return value, reference_type
        return "", self.schema.reference_types[0]


def latest_attempt(
    provider: str, order_bid: str, *, for_update: bool = False, attempt_bid: str = ""
) -> PaymentAttempt | None:
    """Read the original order-domain table; never mix in teacher billing snapshots."""
    query, model, schema = _query_and_schema(provider)
    query = query.filter(model.order_bid == order_bid)
    if attempt_bid:
        query = query.filter(getattr(model, schema.attempt_attribute) == attempt_bid)
    query = query.order_by(model.id.desc())
    if for_update:
        query = query.with_for_update().populate_existing()
    row = query.first()
    return PaymentAttempt(row, schema) if row is not None else None


def pending_attempts(provider: str, order_bid: str) -> list[PaymentAttempt]:
    """Project all attempts that the existing close-before-reprice flow must close."""
    query, model, schema = _query_and_schema(provider)
    rows = (
        query.filter(
            model.order_bid == order_bid, model.status.in_(schema.pending_statuses)
        )
        .order_by(model.id.desc())
        .all()
    )
    return [PaymentAttempt(row, schema) for row in rows]


def bind_native_notification_reference(
    provider: str, snapshot: object, facts: PaymentFacts
) -> None:
    """Validate a bound gateway identity, or bind the first early verified result."""
    reported = facts.provider_reference
    if not reported:
        return
    metadata = _parse_json_payload(snapshot.metadata_json)
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    prepared = metadata.get("prepared_payment_request")
    merchant = getattr(snapshot, native_snapshot_bid_attr(provider))
    if (
        isinstance(prepared, dict)
        and prepared.get("order_bid") == merchant
        and snapshot.provider_attempt_id == merchant
        and not metadata.get("verified_provider_reference")
    ):
        snapshot.provider_attempt_id = reported
        snapshot.metadata_json = _stringify_payload(
            {**metadata, "verified_provider_reference": reported}
        )
        return
    if reported == snapshot.provider_attempt_id:
        return
    message = "Native payment notification reference mismatch"
    raise RuntimeError(message)


def _apply_native_snapshot_update(
    *,
    snapshot: object,
    notification: PaymentNotificationResult,
    source: str,
    facts: PaymentFacts,
    project_status: bool = True,
) -> None:
    """Persist validated facts without decoding the provider's payload again."""
    payload = notification.provider_payload or {}
    raw_status = facts.raw_status or str(notification.status or "")
    incoming_status = {"paid": 1, "refunded": 2, "canceled": 3, "failed": 4}.get(
        facts.state, 0
    )
    if project_status and should_update_native_snapshot_status(
        snapshot.status, incoming_status
    ):
        snapshot.raw_status = raw_status
        snapshot.status = incoming_status
    if notification.charge_id:
        snapshot.transaction_id = notification.charge_id
    if notification.order_bid and not snapshot.provider_attempt_id:
        snapshot.provider_attempt_id = notification.order_bid
    if source == "webhook":
        snapshot.raw_notification = _stringify_payload(payload)
    else:
        snapshot.raw_response = _stringify_payload(payload)
    metadata = _parse_json_payload(snapshot.metadata_json)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["latest_source"] = source
    metadata["latest_provider_payload"] = payload
    snapshot.metadata_json = _stringify_payload(metadata)


def _native_raw_status(
    provider: str,
    payload: dict[str, object],
    fallback: str = "",
) -> str:
    return extract_native_trade_status(provider, payload) or str(fallback or "")


def _native_snapshot_status(
    provider: str,
    payload: dict[str, object],
    raw_status: str,
) -> int:
    if raw_status and not extract_native_trade_status(provider, payload):
        payload = (
            {"trade_status": raw_status}
            if provider == "alipay"
            else {"trade_state": raw_status}
        )
    return native_snapshot_status(provider, payload)


def _is_native_payment_successful(
    provider: str,
    payload: dict[str, object],
) -> bool:
    raw_status = _native_raw_status(provider, payload)
    return _native_snapshot_status(provider, payload, raw_status) == 1


def _extract_native_notification_amount(
    provider: str, payload: dict[str, object]
) -> int | None:
    """Preserve native amount validation through the shared adapter contract."""
    return legacy_native_amount(native_facts(provider, payload))
