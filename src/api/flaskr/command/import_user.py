from flask import Flask
import uuid

from flaskr.service.user.user import generate_temp_user
from flaskr.service.order import init_buy_record
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    upsert_credential,
    update_user_entity_fields,
)
from flaskr.service.common.dtos import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)


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
            aggregate = load_user_aggregate(aggregate.user_bid)

        if not aggregate:
            raise RuntimeError("Failed to resolve user aggregate during import")

        user_id = aggregate.user_bid
        entity = get_user_entity_by_bid(user_id, include_deleted=True)
        updates = {}
        if normalized_mobile:
            updates["identify"] = normalized_mobile
        if aggregate.state == USER_STATE_UNREGISTERED:
            updates["state"] = USER_STATE_REGISTERED
        if user_nick_name:
            updates["nickname"] = user_nick_name
        if updates:
            update_user_entity_fields(entity, **updates)
            aggregate = load_user_aggregate(user_id)
            if not aggregate:
                raise RuntimeError("Failed to refresh user aggregate during import")

        if normalized_mobile:
            upsert_credential(
                app,
                user_bid=user_id,
                provider_name="phone",
                subject_id=normalized_mobile,
                subject_format="phone",
                identifier=normalized_mobile,
                metadata={"course_id": course_id},
                verified=True,
            )
        order = init_buy_record(app, user_id, course_id)
        use_coupon_code(app, user_id, discount_code, order.order_id)
