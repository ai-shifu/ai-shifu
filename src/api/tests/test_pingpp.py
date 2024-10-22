def test_pingxx_order(app):
    from flaskr.service.order.pingxx_order import create_pingxx_order, init_pingxx
    from flaskr.util.uuid import generate_id

    init_pingxx(app)
    order_no = generate_id(app)
    pingxx_id = "app_D8qDWTPyj5yPCGWr"
    product_id = "YourProductId"

    order = create_pingxx_order(
        app,
        order_no,
        pingxx_id,
        "wx_pub_qr",
        100,
        client_ip="127.0.0.1",
        subject="AI编程助手",
        body="AI编程助手",
        extra=dict(product_id=product_id),
    )
    print("=========================wx_pub_qr=========================")
    print(order)


def test_pingxx_ali_order(app):
    from flaskr.service.order.pingxx_order import create_pingxx_order, init_pingxx
    from flaskr.util.uuid import generate_id

    init_pingxx(app)
    order_no = generate_id(app)
    pingxx_id = "app_D8qDWTPyj5yPCGWr"

    order = create_pingxx_order(
        app,
        order_no,
        pingxx_id,
        "alipay_pc_direct",
        100,
        client_ip="123.122.95.34",
        subject="AI",
        body="AI",
        # extra=dict({})
        extra=dict({}),
    )

    print(order)
    order = create_pingxx_order(
        app,
        order_no,
        pingxx_id,
        "alipay_qr",
        100,
        client_ip="123.122.95.34",
        subject="AI",
        body="AI",
        extra=dict({}),
        # extra=dict(qr_pay_mode = 4,qrcode_width=100)
    )
    print("=========================alipay_qr=========================")
    print(order)
