import pytest

pytest.skip(
    "Integration test depends on lesson/discount data not in SQLite unit tests.",
    allow_module_level=True,
)


def test_discount(app):
    from flaskr.service.order.discount import generate_discount_code
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.consts import DISCOUNT_APPLY_TYPE_ALL, DISCOUNT_TYPE_FIXED

    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        generate_discount_code(
            app,
            0.01,
            course_id,
            "2021-01-01",
            "2028-12-31",
            "channel",
            DISCOUNT_TYPE_FIXED,
            DISCOUNT_APPLY_TYPE_ALL,
        )


def test_create_discount(app):
    from flaskr.service.order.discount import generate_discount_code_by_rule
    from flaskr.service.order.models import Discount

    with app.app_context():
        discount = Discount.query.first()
        discount_id = discount.discount_id
        for i in range(10):
            generate_discount_code_by_rule(app, discount_id)


def test_buy_and_pay(app):
    from flaskr.service.order.funs import init_buy_record, generate_charge

    from flaskr.service.user.models import UserInfo as UserEntity
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.models import DiscountRecord
    from flaskr.service.order.consts import DISCOUNT_STATUS_ACTIVE
    from flaskr.service.order.discount import use_discount_code

    with app.app_context():
        user = UserEntity.query.filter(UserEntity.deleted == 0).first()
        course = AICourse.query.first()
        user_id = user.user_bid
        discount_record = DiscountRecord.query.filter(
            DiscountRecord.status == DISCOUNT_STATUS_ACTIVE
        ).first()
        record = init_buy_record(app, user_id, course.course_id)
        use_discount_code(app, user_id, discount_record.discount_code, record.order_id)
        generate_charge(
            app, record.order_id, "alipay_qr", "36.112.103.90", payment_channel=None
        )
