def test_create_active(app):
    from flaskr.service.active.funcs import create_active
    from flaskr.service.active.models import Active
    from flaskr.service.lesson.models import AICourse

    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        active_name = "早鸟价格立减"
        active_desc = "早鸟活动"
        active = Active.query.filter(Active.active_name == active_name).first()
        if active:
            app.logger.info("活动已存在")
            return
        active_id = create_active(
            app, course_id, active_name, active_desc, "2024-01-1", "2024-9-1", 100
        )
        assert active_id is not None


def test_create_order_with_active(app):
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order import init_buy_record
    from flaskr.service.user import generate_temp_user
    from flaskr.util import generate_id
    from flaskr.service.order.models import DiscountRecord
    from flaskr.service.order.discount import use_discount_code

    with app.app_context():

        user = generate_temp_user(app, generate_id(app), str(123456))
        user_id = user.userInfo.user_id
        course = AICourse.query.first()
        course_id = course.course_id
        order = init_buy_record(app, user_id, course_id)

        discount_record = DiscountRecord.query.filter(
            DiscountRecord.status == 902, DiscountRecord.discount_value == 200
        ).first()
        # assert order_id is not None

        order = use_discount_code(
            app, user_id, discount_record.discount_code, order.order_id
        )
        app.logger.info("order: {}".format(order.__json__()))
