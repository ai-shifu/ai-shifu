from flask import Flask, request
from flaskr.service.common.models import raise_param_error, raise_error
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.route.common import make_common_response
from flaskr.service.order import (
    generate_charge,
    query_buy_record,
    init_buy_record,
    handle_stripe_webhook,
    get_payment_details,
    sync_stripe_checkout_session,
)
from flaskr.service.order.admin import (
    get_order_detail,
    import_activation_orders,
    list_orders,
)
from flaskr.service.learn.learn_funcs import get_shifu_info
from flaskr.common.shifu_context import with_shifu_context


def register_order_handler(app: Flask, path_prefix: str):
    def _require_creator():
        if not request.user.is_creator:
            raise_error("server.shifu.noPermission")

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
    @with_shifu_context()
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

    @app.route(path_prefix + "/stripe/sync", methods=["POST"])
    def stripe_sync():
        """
        同步 Stripe 支付状态
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
                    session_id:
                        type: string
                        description: Stripe checkout session id
        responses:
            200:
                description: 同步成功
        """

        payload = request.get_json() or {}
        order_id = payload.get("order_id", "")
        if not order_id:
            raise_param_error("order_id")
        session_id = payload.get("session_id")
        user_id = request.user.user_id
        return make_common_response(
            sync_stripe_checkout_session(
                app,
                order_id,
                session_id=session_id,
                expected_user=user_id,
            )
        )

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

    @app.route(path_prefix + "/admin/orders", methods=["GET"])
    def admin_order_list():
        """
        Admin order list
        ---
        tags:
            - 订单
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: order_bid
              type: string
              required: false
            - name: user_bid
              type: string
              required: false
              description: Email or mobile (user_identify)
            - name: shifu_bid
              type: string
              required: false
              description: Comma-separated course IDs
            - name: status
              type: integer
              required: false
            - name: payment_channel
              type: string
              required: false
            - name: start_time
              type: string
              required: false
              description: Order created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: Order created end date (YYYY-MM-DD)
        responses:
            200:
                description: List orders
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/PageNationDTO"
        """
        _require_creator()
        page_index = request.args.get("page_index", 1)
        page_size = request.args.get("page_size", 20)
        try:
            page_index = int(page_index)
            page_size = int(page_size)
        except ValueError:
            raise_param_error("page_index or page_size is not a number")
        if page_index < 1 or page_size < 1:
            raise_param_error("page_index or page_size is less than 1")

        filters = {
            "order_bid": request.args.get("order_bid", ""),
            "user_bid": request.args.get("user_bid", ""),
            "shifu_bid": request.args.get("shifu_bid", ""),
            "status": request.args.get("status"),
            "payment_channel": request.args.get("payment_channel", ""),
            "start_time": request.args.get("start_time", ""),
            "end_time": request.args.get("end_time", ""),
        }
        user_id = request.user.user_id
        return make_common_response(
            list_orders(app, user_id, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/orders/import-activation", methods=["POST"])
    def admin_import_activation():
        """
        Admin import activation order
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
                    mobile:
                        type: string
                        description: User mobile
                    course_id:
                        type: string
                        description: Course id
                    user_nick_name:
                        type: string
                        description: User nickname
        responses:
            200:
                description: Import success
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
                                    properties:
                                        order_bid:
                                            type: string
        """
        _require_creator()
        payload = request.get_json() or {}
        mobile_field = str(payload.get("mobile", "")).strip()
        course_id = str(payload.get("course_id", "")).strip()
        user_nick_name = payload.get("user_nick_name")

        if not mobile_field:
            raise_param_error("mobile")
        if not course_id:
            raise_param_error("course_id")

        mobiles = [item.strip() for item in mobile_field.split(",") if item.strip()]
        if not mobiles:
            raise_param_error("mobile")
        if len(mobiles) > 50:
            raise_param_error("mobile limit 50")

        # Validate course exists before iterating mobiles to avoid repeated errors
        get_shifu_info(app, course_id, False)

        return make_common_response(
            import_activation_orders(app, mobiles, course_id, user_nick_name)
        )

    @app.route(path_prefix + "/admin/orders/<order_bid>", methods=["GET"])
    def admin_order_detail(order_bid: str):
        """
        Admin order detail
        ---
        tags:
            - 订单
        parameters:
            - name: order_bid
              type: string
              required: true
        responses:
            200:
                description: Order detail
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/OrderAdminDetailDTO"
        """
        _require_creator()
        if not order_bid:
            raise_param_error("order_bid")
        user_id = request.user.user_id
        return make_common_response(get_order_detail(app, user_id, order_bid))

    return app
