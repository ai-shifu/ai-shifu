from flask import Flask
import uuid

from flaskr.service.user import generate_temp_user
from flaskr.service.order import init_buy_record
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    update_user_entity_fields,
)
from flaskr.service.common.dtos import USER_STATE_REGISTERED


def import_user(
    app: Flask, mobile, course_id, discount_code="web", user_nick_name=None
):
    """Import user and enable course"""
    app.logger.info(f"import_user: {mobile}, {course_id}")
    with app.app_context():
        normalized_mobile = str(mobile or "").strip()
        aggregate = load_user_aggregate_by_identifier(
            normalized_mobile, providers=["phone"]
        )

        if not aggregate:
            temp_id = uuid.uuid4().hex
            generate_temp_user(app, temp_id)
            aggregate = load_user_aggregate_by_identifier(
                normalized_mobile, providers=["phone"]
            )
            if not aggregate:
                defaults = {
                    "nickname": user_nick_name or normalized_mobile or temp_id,
                    "language": "en-US",
                    "state": USER_STATE_REGISTERED,
                }
                aggregate, _ = ensure_user_for_identifier(
                    app,
                    provider="phone",
                    identifier=normalized_mobile or temp_id,
                    defaults=defaults,
                )
        else:
            entity = get_user_entity_by_bid(aggregate.user_bid, include_deleted=True)
            updates = {"identify": normalized_mobile}
            if aggregate.state == USER_STATE_UNREGISTERED:
                updates["state"] = USER_STATE_REGISTERED
            if user_nick_name:
                updates["nickname"] = user_nick_name
            update_user_entity_fields(entity, **updates)
            aggregate = load_user_aggregate(aggregate.user_bid)

        if not aggregate:
            raise RuntimeError("Failed to resolve user aggregate during import")

        user_id = aggregate.user_bid
        order = init_buy_record(app, user_id, course_id)
        use_coupon_code(app, user_id, discount_code, order.order_id)
