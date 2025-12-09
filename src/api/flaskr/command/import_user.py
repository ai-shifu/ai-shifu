from flask import Flask

from flaskr.service.order import init_buy_record
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    upsert_credential,
)
from flaskr.service.common.dtos import (
    USER_STATE_REGISTERED,
)


def import_user(
    app: Flask, mobile, course_id, discount_code="web", user_nick_name=None
):
    """Import user and enable course"""
    app.logger.info(f"import_user: {mobile}, {course_id}")
    with app.app_context():
        normalized_mobile = str(mobile or "").strip()
        if not normalized_mobile:
            raise RuntimeError("Mobile must not be empty for import_user")

        # Ensure there is a canonical user bound to this phone number, and that
        # the canonical record tracks the phone in ``user_identify`` together
        # with the desired nickname and registered state.
        defaults = {
            "identify": normalized_mobile,
            "nickname": user_nick_name or normalized_mobile,
            "language": "en-US",
            "state": USER_STATE_REGISTERED,
        }
        aggregate, _ = ensure_user_for_identifier(
            app,
            provider="phone",
            identifier=normalized_mobile,
            defaults=defaults,
        )

        if not aggregate:
            raise RuntimeError("Failed to resolve user aggregate during import")

        user_id = aggregate.user_bid
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
