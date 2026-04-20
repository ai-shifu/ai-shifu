import json

from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
from flask import Flask


def send_sms_ali(
    app: Flask,
    mobile: str,
    *,
    template_code: str,
    template_params: dict[str, str],
    sign_name: str | None = None,
) -> dysmsapi_20170525_models.SendSmsResponse | None:
    if not app.config.get(
        "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID", None
    ) or not app.config.get("ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET", None):
        app.logger.warning(
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID or "
            "ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET not configured"
        )
        return None
    resolved_template_code = str(template_code or "").strip()
    resolved_sign_name = str(
        sign_name or app.config["ALIBABA_CLOUD_SMS_SIGN_NAME"]
    ).strip()
    if not resolved_template_code:
        app.logger.warning("template_code is required for Aliyun SMS")
        return None
    if not resolved_sign_name:
        app.logger.warning("ALIBABA_CLOUD_SMS_SIGN_NAME not configured")
        return None
    config = open_api_models.Config(
        access_key_id=app.config["ALIBABA_CLOUD_SMS_ACCESS_KEY_ID"],
        access_key_secret=app.config["ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET"],
    )
    config.endpoint = "dysmsapi.aliyuncs.com"
    client = Dysmsapi20170525Client(config)
    send_sms_request = dysmsapi_20170525_models.SendSmsRequest()
    send_sms_request.sign_name = resolved_sign_name
    send_sms_request.template_code = resolved_template_code
    send_sms_request.phone_numbers = mobile
    send_sms_request.template_param = json.dumps(
        template_params,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    runtime = util_models.RuntimeOptions()
    try:
        res = client.send_sms_with_options(send_sms_request, runtime)
        return res
    except Exception as error:
        app.logger.error(error.message)
        app.logger.error(error.data.get("Recommend"))
        UtilClient.assert_as_string(error.message)
    return None


def send_sms_code_ali(
    app: Flask, mobile: str, check_code: str
) -> dysmsapi_20170525_models.SendSmsResponse | None:
    return send_sms_ali(
        app,
        mobile,
        template_code=app.config["ALIBABA_CLOUD_SMS_TEMPLATE_CODE"],
        template_params={"code": check_code},
    )
