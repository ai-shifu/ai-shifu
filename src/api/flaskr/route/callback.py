from flask import Flask, jsonify, make_response, request

from flaskr.service.billing.webhooks import (
    apply_billing_native_notification,
    handle_billing_pingxx_webhook,
)
from flaskr.service.order.payment_providers import get_payment_provider

from .common import bypass_token_validation
from ..service.order import (
    success_buy_record_from_native,
    success_buy_record_from_pingxx,
)


def register_callback_handler(app: Flask, path_prefix: str):
    # pingxx支付回调
    @app.route(path_prefix + "/pingxx-callback", methods=["POST"])
    @bypass_token_validation
    def pingxx_callback():
        body = request.get_json()
        app.logger.info("pingxx-callback: %s", body)
        type = body.get("type", "")
        if type == "charge.succeeded":
            order_no = body.get("data", {}).get("object", {}).get("order_no", "")
            id = body.get("data", {}).get("object", {}).get("id", "")
            app.logger.info("pingxx-callback: charge.succeeded order_no: %s", order_no)
            billing_result = handle_billing_pingxx_webhook(app, body)
            if not billing_result.matched:
                success_buy_record_from_pingxx(app, id, body)
            # 处理支付成功逻辑
            # do something

        response = make_response("pingxx callback success")
        response.mimetype = "text/plain"
        return response

    @app.route(path_prefix + "/alipay-notify", methods=["POST"])
    @bypass_token_validation
    def alipay_notify():
        form_payload = request.form.to_dict(flat=True)
        app.logger.info("alipay-notify: %s", form_payload)
        provider = get_payment_provider("alipay")
        try:
            notification = provider.handle_notification(
                payload=form_payload,
                app=app,
            )
            billing_result = apply_billing_native_notification(
                app,
                "alipay",
                notification,
            )
            if not billing_result.matched:
                matched = success_buy_record_from_native(
                    app,
                    "alipay",
                    notification,
                )
                if not matched:
                    return _plain_text_response("failure")
        except Exception as exc:
            app.logger.exception("alipay-notify failed: %s", exc)
            return _plain_text_response("failure")
        return _plain_text_response("success")

    @app.route(path_prefix + "/wechatpay-notify", methods=["POST"])
    @bypass_token_validation
    def wechatpay_notify():
        raw_body = request.get_data() or b""
        app.logger.info("wechatpay-notify: %s", raw_body)
        provider = get_payment_provider("wechatpay")
        try:
            notification = provider.verify_webhook(
                headers=dict(request.headers),
                raw_body=raw_body,
                app=app,
            )
            billing_result = apply_billing_native_notification(
                app,
                "wechatpay",
                notification,
            )
            if not billing_result.matched:
                matched = success_buy_record_from_native(
                    app,
                    "wechatpay",
                    notification,
                )
                if not matched:
                    return (
                        jsonify({"code": "FAIL", "message": "order not found"}),
                        404,
                    )
        except Exception as exc:
            app.logger.exception("wechatpay-notify failed: %s", exc)
            return jsonify({"code": "FAIL", "message": str(exc)}), 400
        return jsonify({"code": "SUCCESS", "message": "成功"})

    return app


def _plain_text_response(value: str):
    response = make_response(value)
    response.mimetype = "text/plain"
    return response
