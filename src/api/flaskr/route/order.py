from flask import Flask, request
from flaskr.service.common.models import raise_param_error
from flaskr.service.order.discount import use_discount_code
from flaskr.route.common import make_common_response
from flaskr.service.order import (
    generate_charge,
    query_buy_record,
    init_buy_record,
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
                        description: 支付渠道,目前支持wx_pub_qr,alipay_qr
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
        order_id = request.get_json().get("order_id", "")
        channel = request.get_json().get("channel", "")
        client_ip = request.client_ip
        return make_common_response(generate_charge(app, order_id, channel, client_ip))

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
            use_discount_code(app, user_id, discount_code, order_id)
        )

    return app
