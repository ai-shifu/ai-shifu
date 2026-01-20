import pytest

pytest.skip(
    "Integration test requires lesson module and payment setup.",
    allow_module_level=True,
)


# "66de5cb18ccf41f18aed9a83efba92ac"


def test_buy_and_pay(app):
    from flaskr.service.order.funs import init_buy_record, generate_charge

    from flaskr.service.user.models import UserInfo as UserEntity
    from flaskr.service.lesson.models import AICourse

    with app.app_context():
        user = UserEntity.query.filter(
            UserEntity.user_bid == "66de5cb18ccf41f18aed9a83efba92ac"
        ).first()
        course = AICourse.query.first()
        user_id = user.user_bid
        record = init_buy_record(app, user_id, course.course_id)
        generate_charge(
            app, record.order_id, "wx_wap", "116.179.37.55", payment_channel=None
        )
