def test_buy_and_pay(app):
    from flaskr.service.order.funs import (
        init_buy_record,
        generate_charge,
        query_buy_record,
    )

    from flaskr.service.user.models import UserInfo as UserEntity
    from flaskr.service.shifu.models import PublishedShifu
    from flaskr.service.order.models import Order
    from flaskr.dao import db

    with app.app_context():
        user = UserEntity.query.filter(UserEntity.deleted == 0).first()
        shifu = (
            PublishedShifu.query.filter(
                PublishedShifu.price > 0,
                PublishedShifu.deleted == 0,
            )
            .order_by(PublishedShifu.id.desc())
            .first()
        )
        user_id = user.user_bid

        Order.query.filter(
            Order.user_bid == user_id,
            Order.shifu_bid == shifu.shifu_bid,
        ).delete()
        db.session.commit()

        record = init_buy_record(app, user_id, shifu.shifu_bid)

        print(record)
        print(record.__json__())
        record = query_buy_record(app, record.order_id)
        print(record.__json__())

        res = generate_charge(app, record.order_id, "wx_pub_qr", "237.0.0.1")
        print(res.__json__())
