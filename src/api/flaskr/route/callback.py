"""Expose callback HTTP routes."""

from flask import Flask, Response, jsonify, make_response, request

from flaskr.service.billing.customization import (
    build_provider_config_overrides,
    resolve_provider_credential_context,
)
from flaskr.service.billing.webhooks import apply_billing_native_notification
from flaskr.service.config import config_overrides
from flaskr.service.order import handle_stripe_webhook, success_buy_record_from_native
from flaskr.service.order.models import Order
from flaskr.service.order.payment_providers import get_payment_provider
from flaskr.service.order.raw_snapshots import native_snapshot_model

from .common import bypass_token_validation


def register_callback_handler(app: Flask, path_prefix: str) -> Flask:
    """Register the callback routes on the Flask application."""

    @app.route("/api/order/webhooks/<provider_name>/<callback_token>", methods=["POST"])
    @bypass_token_validation
    def scoped_payment_webhook(
        provider_name: str, callback_token: str
    ) -> Response | tuple[Response, int]:
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
                billing_result = apply_billing_native_notification(
                    app, provider_name, notification
                )
                if not billing_result.matched:
                    success_buy_record_from_native(app, provider_name, notification)
                if provider_name == "alipay":
                    return _plain_text_response("success")
                return jsonify({"code": "SUCCESS", "message": "成功"})
            except Exception:
                app.logger.exception("Scoped %s webhook failed", provider_name)
                if provider_name == "alipay":
                    return _plain_text_response("failure")
                return jsonify({"code": "FAIL", "message": "processing error"}), 400

    @app.route(path_prefix + "/alipay-notify", methods=["POST"])
    @bypass_token_validation
    def alipay_notify() -> Response:
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
        except Exception:
            app.logger.exception("alipay-notify failed")
            return _plain_text_response("failure")
        return _plain_text_response("success")

    @app.route(path_prefix + "/wechatpay-notify", methods=["POST"])
    @bypass_token_validation
    def wechatpay_notify() -> Response | tuple[Response, int]:
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
        except Exception:
            app.logger.exception("wechatpay-notify failed")
            return jsonify({"code": "FAIL", "message": "processing error"}), 400
        return jsonify({"code": "SUCCESS", "message": "成功"})

    return app


def _plain_text_response(value: str) -> Response:
    response = make_response(value)
    response.mimetype = "text/plain"
    return response


def _require_matching_integration(
    provider_name: str,
    provider_order_bid: str,
    creator_bid: str,
    integration_bid: str,
) -> None:
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
        message = "Payment integration does not match order"
        raise RuntimeError(message)
