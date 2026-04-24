from flask import Flask, make_response, request

from flaskr.service.billing.webhooks import handle_billing_pingxx_webhook

from .common import bypass_token_validation
from ..service.order import success_buy_record_from_pingxx


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

    return app
