from flask import Flask, request
from flaskr.service.common.models import raise_param_error
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.route.common import make_common_response
from flaskr.service.order import (
    generate_charge,
    query_buy_record,
    init_buy_record,
    handle_stripe_webhook,
    get_payment_details,
)


def register_order_handler(app: Flask, path_prefix: str):
    @app.route(path_prefix + "/reqiure-to-pay", methods=["POST"])
    def reqiure_to_pay():
        """
        请求支付
        ---
        tags:
            - 订单
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    order_id:
                        type: string
                        description: 订单id
                    channel:
                        type: string
                        description: 支付渠道。Ping++通道请输入wx_pub_qr、alipay_qr等；Stripe通道请输入stripe或stripe:checkout_session等格式
                    payment_channel:
                        type: string
                        description: 目标支付提供方，可选值为pingxx或stripe（不填则沿用订单记录）
        responses:
            200:
                description: 请求支付成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/BuyRecordDTO"

        """
        payload = request.get_json() or {}
        order_id = payload.get("order_id", "")
        channel = payload.get("channel", "")
        payment_channel = payload.get("payment_channel")
        client_ip = request.client_ip
        return make_common_response(
            generate_charge(
                app,
                order_id,
                channel,
                client_ip,
                payment_channel=payment_channel,
            )
        )

    @app.route(path_prefix + "/init-order", methods=["POST"])
    def init_order():
        """
        初始化订单
        ---
        tags:

            - 订单
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    course_id:
                        type: string
                        description: 课程id
        responses:
            200:
                description: 初始化订单成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/AICourseBuyRecordDTO"

        """
        user_id = request.user.user_id
        course_id = request.get_json().get("course_id", "")
        return make_common_response(init_buy_record(app, user_id, course_id))

    @app.route(path_prefix + "/query-order", methods=["POST"])
    def query_order():
        """
        查询订单
        ---
        tags:
            - 订单
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    order_id:
                        type: string
                        description: 订单id
        responses:

            200:
                description: 查询订单成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/AICourseBuyRecordDTO"

        """
        order_id = request.get_json().get("order_id", "")
        return make_common_response(query_buy_record(app, order_id))

    @app.route(path_prefix + "/apply-discount", methods=["POST"])
    def apply_discount():
        """
        使用折扣码
        ---
        tags:
            - 订单
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    discount_code:
                        type: string
                        description: 折扣码
                    order_id:
                        type: string
                        description: 订单id
        responses:
            200:
                description: 使用折扣码成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/AICourseBuyRecordDTO"

        """
        discount_code = request.get_json().get("discount_code", "")
        if not discount_code:
            raise_param_error("discount_code")
        order_id = request.get_json().get("order_id", "")
        if not order_id:
            raise_param_error("order_id")
        user_id = request.user.user_id
        return make_common_response(
            use_coupon_code(app, user_id, discount_code, order_id)
        )

    @app.route(path_prefix + "/payment-detail", methods=["POST"])
    def payment_detail():
        """
        查询支付详情
        ---
        tags:
            - 订单
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    order_id:
                        type: string
                        description: 订单id
        responses:
            200:
                description: 查询支付详情成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    type: object
        """

        order_id = request.get_json().get("order_id", "")
        if not order_id:
            raise_param_error("order_id")
        return make_common_response(get_payment_details(app, order_id))

    @app.route(path_prefix + "/stripe/webhook", methods=["POST"])
    def stripe_webhook():
        """
        Stripe webhook接入占位
        ---
        tags:
            - 订单
        responses:
            202:
                description: Webhook已接收，具体逻辑待实现
        """

        sig_header = request.headers.get("Stripe-Signature", "")
        raw_body = request.get_data() or b""
        payload, status_code = handle_stripe_webhook(app, raw_body, sig_header)
        body = make_common_response(payload)
        return app.response_class(body, status=status_code, mimetype="application/json")

    return app
