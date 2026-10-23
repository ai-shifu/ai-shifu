"""Preserve the legacy Ping++ callback protocol and side-effect compatibility."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import redis_cache
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.service.user.consts import USER_STATE_PAID
from flaskr.util.datetime import now_utc

from .consts import ORDER_STATUS_SUCCESS
from .models import Order, PingxxOrder
from .payment_policy import purchase_attempt_can_complete, purchase_attempt_matches
from .raw_snapshots import legacy_pingxx_snapshot_query

if TYPE_CHECKING:
    from flask import Flask

    from .funs import AICourseBuyRecordDTO


def success_buy_record_from_pingxx(
    app: Flask, charge_id: str, body: dict
) -> AICourseBuyRecordDTO | None:
    """Success buy record from pingxx."""
    from .funs import (
        _app_context_scope,
        get_shifu_creator_bid,
        query_buy_record,
        send_order_feishu,
        set_shifu_context,
        set_user_state,
    )

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
            lock = redis_cache.lock(
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
                with unit_of_work():
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
                        set_shifu_context(
                            buy_record.shifu_bid,
                            get_shifu_creator_bid(app, buy_record.shifu_bid),
                        )

                    latest = (
                        legacy_pingxx_snapshot_query()
                        .filter(PingxxOrder.order_bid == pingxx_order.order_bid)
                        .order_by(PingxxOrder.id.desc())
                        .with_entities(PingxxOrder.id)
                        .first()
                    )
                    matches = buy_record is not None and purchase_attempt_matches(
                        price=buy_record.paid_price,
                        attempt_amount=int(pingxx_order.amount or 0),
                        attempt_id=pingxx_order.id,
                        latest_id=latest[0] if latest else None,
                    )
                    if not buy_record or not purchase_attempt_can_complete(
                        order_status=buy_record.status,
                        attempt_status=pingxx_order.status,
                        current_attempt=matches,
                    ):
                        # Pre-uow behavior: the snapshot mutation was never
                        # committed on this path, so do not mutate it at all.
                        app.logger.error("record:%s not found", pingxx_order.order_bid)
                        return None
                    pingxx_order.update = now_utc()
                    pingxx_order.status = 1
                    pingxx_order.charge_object = json.dumps(body)
                    try:
                        set_user_state(buy_record.user_bid, USER_STATE_PAID)
                    except Exception:
                        app.logger.exception("update user state error")
                    buy_record.status = ORDER_STATUS_SUCCESS
                send_order_feishu(app, buy_record.order_bid)
                return query_buy_record(app, buy_record.order_bid)
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
