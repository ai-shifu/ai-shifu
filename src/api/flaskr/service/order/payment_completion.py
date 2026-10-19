"""Mark legacy orders paid from provider notifications."""

import decimal
import json

from flask import Flask
from flaskr.dao import db, uow
from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.order.consts import (
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.funs_lookup import order_funs
from flaskr.service.order.legacy_order_dtos import (
    AICourseBuyRecordDTO,
)
from flaskr.service.order.models import (
    Order,
    PingxxOrder,
)
from flaskr.service.order.payment_attempts import (
    _apply_native_snapshot_update,
    _extract_native_notification_amount,
    _is_native_payment_successful,
)
from flaskr.service.order.payment_lifecycle import (
    _assert_payment_lifecycle_lock_owned,
)
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
)
from flaskr.service.order.raw_snapshots import (
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    native_snapshot_model,
)
from flaskr.service.user.consts import (
    USER_STATE_PAID,
)
from flaskr.util.datetime import now_utc

# Shared session-scope guard; see flaskr/dao/uow.py for the rationale.
_app_context_scope = app_context_scope


def success_buy_record_from_native(
    app: Flask,
    provider_name: str,
    notification: PaymentNotificationResult,
) -> bool:
    """Apply a successful native-payment notification to the purchase record."""
    uow.require_transaction_owner("native payment notification", app)
    with _app_context_scope(app), order_funs.unit_of_work(discard=True):
        provider = str(provider_name or "").strip().lower()
        if provider not in {"alipay", "wechatpay"}:
            raise_error("server.pay.payChannelNotSupport")
        provider_attempt_id = str(notification.order_bid or "").strip()
        transaction_id = str(notification.charge_id or "").strip()
        native_model = native_snapshot_model(provider)
        query = legacy_native_snapshot_query(provider)
        if provider_attempt_id:
            native_order = (
                query.filter(native_model.provider_attempt_id == provider_attempt_id)
                .order_by(native_model.id.desc())
                .first()
            )
        elif transaction_id:
            native_order = (
                query.filter(native_model.transaction_id == transaction_id)
                .order_by(native_model.id.desc())
                .first()
            )
        else:
            native_order = None
        if native_order is None:
            return False
        order_bid = str(native_order.order_bid or "")
        native_order_id = native_order.id

    with (
        _app_context_scope(app),
        order_funs.payment_lifecycle_lock(order_bid) as lifecycle_lease,
        order_funs.unit_of_work(),
    ):
        buy_record: Order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if not buy_record:
            return False

        native_order = native_model.query.filter(
            native_model.id == native_order_id,
            native_model.deleted == 0,
        ).first()
        if native_order is None:
            return False

        actual_amount = _extract_native_notification_amount(
            provider,
            notification.provider_payload or {},
        )
        if actual_amount is not None and int(native_order.amount or 0) != actual_amount:
            message = "Native payment amount mismatch"
            raise RuntimeError(message)

        was_pending_attempt = native_order.status == 0
        _apply_native_snapshot_update(
            snapshot=native_order,
            provider=provider,
            notification=notification,
            source="webhook",
        )
        db.session.add(native_order)

        if (
            _is_native_payment_successful(
                provider,
                notification.provider_payload or {},
            )
            and was_pending_attempt
            and native_order.id
            == (
                legacy_native_snapshot_query(provider)
                .filter(native_model.order_bid == native_order.order_bid)
                .order_by(native_model.id.desc())
                .with_entities(native_model.id)
                .first()
                or (None,)
            )[0]
            and (
                decimal.Decimal(buy_record.paid_price or 0) <= 0
                or int(native_order.amount or 0)
                == int(decimal.Decimal(buy_record.paid_price) * 100)
            )
            and buy_record.status in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}
        ):
            order_funs.success_buy_record(app, buy_record.order_bid)
        _assert_payment_lifecycle_lock_owned()
        lifecycle_lease.release_checked()
        return True


def success_buy_record_from_pingxx(
    app: Flask, charge_id: str, body: dict
) -> AICourseBuyRecordDTO | None:
    """Success buy record from pingxx."""
    with _app_context_scope(app):
        pingxx_order = (
            legacy_pingxx_snapshot_query()
            .filter(PingxxOrder.charge_id == charge_id)
            .first()
        )
        if not pingxx_order:
            return None
        try:
            # Payment callbacks must never fall back to a process-local lock.
            lock = order_funs.redis_cache.lock(
                "success_buy_record_from_pingxx" + charge_id,
                timeout=10,
                blocking_timeout=10,
            )
            acquired = bool(lock and lock.acquire(blocking=True))
        except Exception:
            app.logger.exception('lock acquisition failed for charge:"%s"', charge_id)
            raise_error("server.order.orderStatusError")

        if acquired:
            try:
                app.logger.info('success buy record from pingxx charge:"%s"', charge_id)
                with order_funs.unit_of_work():
                    pingxx_order = (
                        legacy_pingxx_snapshot_query()
                        .filter(PingxxOrder.charge_id == charge_id)
                        .first()
                    )
                    if not pingxx_order:
                        return None
                    buy_record: Order = Order.query.filter(
                        Order.order_bid == pingxx_order.order_bid,
                    ).first()
                    if buy_record:
                        order_funs.set_shifu_context(
                            buy_record.shifu_bid,
                            order_funs.get_shifu_creator_bid(app, buy_record.shifu_bid),
                        )

                    if not (
                        buy_record
                        and pingxx_order.status == 0
                        and pingxx_order.id
                        == (
                            legacy_pingxx_snapshot_query()
                            .filter(PingxxOrder.order_bid == pingxx_order.order_bid)
                            .order_by(PingxxOrder.id.desc())
                            .with_entities(PingxxOrder.id)
                            .first()
                            or (None,)
                        )[0]
                        and (
                            decimal.Decimal(buy_record.paid_price or 0) <= 0
                            or int(pingxx_order.amount or 0)
                            == int(decimal.Decimal(buy_record.paid_price) * 100)
                        )
                        and buy_record.status
                        in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}
                    ):
                        # Pre-uow behavior: the snapshot mutation was never
                        # committed on this path, so do not mutate it at all.
                        app.logger.error("record:%s not found", pingxx_order.order_bid)
                        return None
                    pingxx_order.update = now_utc()
                    pingxx_order.status = 1
                    pingxx_order.charge_object = json.dumps(body)
                    try:
                        order_funs.set_user_state(buy_record.user_bid, USER_STATE_PAID)
                    except Exception:
                        app.logger.exception("update user state error")
                    buy_record.status = ORDER_STATUS_SUCCESS
                order_funs.send_order_feishu(app, buy_record.order_bid)
                return order_funs.query_buy_record(app, buy_record.order_bid)
            except Exception:
                app.logger.exception(
                    'success buy record from pingxx charge:"%s"', charge_id
                )
            finally:
                lock.release()
        else:
            app.logger.error('lock failed for charge:"%s"', charge_id)
            raise_error("server.order.orderStatusError")
    return None
