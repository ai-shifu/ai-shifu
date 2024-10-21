def test_buy_and_pay(app):
    from flaskr.service.order.funs import init_buy_record, generate_charge
    from flaskr.util.uuid import generate_id

    from flaskr.service.user.models import User
    from flaskr.service.lesson.models import AICourse

    with app.app_context():
        user = User.query.first()
        course = AICourse.query.first()
        price = course.course_price
        user_id = user.user_id
        record = init_buy_record(app, user_id, course.course_id)
        charge = generate_charge(app, record.order_id, "wx_pub_qr", "237.0.0.1")
