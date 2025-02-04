def test_feishu(app):
    from flaskr.service.order.funs import send_order_feishu

    with app.app_context():
        send_order_feishu(app, "925a8aef314643c999f49c1a971f6249")
