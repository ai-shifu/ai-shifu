from flask import Flask, jsonify, make_response, request

from flaskr.service.billing.webhooks import (
    apply_billing_native_notification,
    handle_billing_pingxx_webhook,
)
from flaskr.service.order.payment_providers import get_payment_provider
from flaskr.service.config import config_overrides
from flaskr.service.billing.customization import (
    build_provider_config_overrides,
    resolve_provider_credential_context,
)
from flaskr.service.order.models import Order, PingxxOrder
from flaskr.service.order.raw_snapshots import native_snapshot_model

from .common import bypass_token_validation
from ..service.order import (
    success_buy_record_from_native,
    success_buy_record_from_pingxx,
    handle_stripe_webhook,
)


def register_callback_handler(app: Flask, path_prefix: str):
    @app.route("/api/order/webhooks/<provider_name>/<callback_token>", methods=["POST"])
    @bypass_token_validation
    def scoped_payment_webhook(provider_name: str, callback_token: str):
        context = resolve_provider_credential_context(
            app,
            provider=provider_name,
            callback_token=callback_token,
        )
        if context is None or context.provider != provider_name:
            return jsonify({"code": "FAIL", "message": "invalid callback"}), 400
        raw_body = request.get_data() or b""
        with config_overrides(build_provider_config_overrides(context)):
            if provider_name == "stripe":
                payload, status = handle_stripe_webhook(
                    app,
                    raw_body,
                    request.headers.get("Stripe-Signature", ""),
                    expected_integration_bid=context.integration_bid,
                )
                return jsonify(payload), status

            provider = get_payment_provider(provider_name)
            try:
                notification = provider.verify_webhook(
                    headers=dict(request.headers),
                    raw_body=raw_body,
                    app=app,
                )
                _require_matching_integration(
                    provider_name,
                    notification.order_bid,
                    context.creator_bid,
                    context.integration_bid,
                )
                if provider_name == "pingxx":
                    body = notification.provider_payload
                    if notification.status == "charge.succeeded":
                        billing_result = handle_billing_pingxx_webhook(app, body)
                        if not billing_result.matched:
                            success_buy_record_from_pingxx(
                                app, notification.charge_id or "", body
                            )
                    return _plain_text_response("pingxx callback success")

                billing_result = apply_billing_native_notification(
                    app, provider_name, notification
                )
                if not billing_result.matched:
                    success_buy_record_from_native(app, provider_name, notification)
                if provider_name == "alipay":
                    return _plain_text_response("success")
                return jsonify({"code": "SUCCESS", "message": "成功"})
            except Exception as exc:
                app.logger.exception("Scoped %s webhook failed: %s", provider_name, exc)
                if provider_name == "alipay":
                    return _plain_text_response("failure")
                return jsonify({"code": "FAIL", "message": "processing error"}), 400

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
                    app.logger.warning(
                        "alipay-notify unmatched local payment provider=%s order_bid=%s charge_id=%s status=%s reason=%s",
                        "alipay",
                        notification.order_bid,
                        notification.charge_id,
                        notification.status,
                        "billing_and_order_not_matched",
                    )
                    return _plain_text_response("success")
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
                    app.logger.warning(
                        "wechatpay-notify unmatched local payment provider=%s order_bid=%s charge_id=%s status=%s reason=%s",
                        "wechatpay",
                        notification.order_bid,
                        notification.charge_id,
                        notification.status,
                        "billing_and_order_not_matched",
                    )
                    return jsonify({"code": "SUCCESS", "message": "成功"})
        except Exception as exc:
            app.logger.exception("wechatpay-notify failed: %s", exc)
            return jsonify({"code": "FAIL", "message": "processing error"}), 400
        return jsonify({"code": "SUCCESS", "message": "成功"})

    return app


def _plain_text_response(value: str):
    response = make_response(value)
    response.mimetype = "text/plain"
    return response


def _require_matching_integration(
    provider_name: str,
    provider_order_bid: str,
    creator_bid: str,
    integration_bid: str,
) -> None:
    local_order_bid = ""
    if provider_name == "pingxx":
        snapshot = (
            PingxxOrder.query.filter(
                PingxxOrder.transaction_no == provider_order_bid,
                PingxxOrder.biz_domain == "order",
            )
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        local_order_bid = str(getattr(snapshot, "order_bid", "") or "")
    else:
        model = native_snapshot_model(provider_name)
        snapshot = (
            model.query.filter(
                model.provider_attempt_id == provider_order_bid,
                model.biz_domain == "order",
            )
            .order_by(model.id.desc())
            .first()
        )
        local_order_bid = str(getattr(snapshot, "order_bid", "") or "")
    order = Order.query.filter(Order.order_bid == local_order_bid).first()
    if (
        order is None
        or order.creator_bid != creator_bid
        or order.payment_integration_bid != integration_bid
    ):
        raise RuntimeError("Payment integration does not match order")
