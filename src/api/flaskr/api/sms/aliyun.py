from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
from flask import Flask


def send_sms_code_ali(
    app: Flask, mobile: str, check_code: str
) -> dysmsapi_20170525_models.SendSmsResponse | None:
    config = open_api_models.Config(
        access_key_id=app.config["ALIBABA_CLOUD_ACCESS_KEY_ID"],
        access_key_secret=app.config["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
    )
    config.endpoint = "dysmsapi.aliyuncs.com"
    client = Dysmsapi20170525Client(config)
    send_sms_request = dysmsapi_20170525_models.SendSmsRequest()
    send_sms_request.sign_name = app.config["ALIBABA_CLOUD_SMS_SIGN_NAME"]
    send_sms_request.template_code = app.config["ALIBABA_CLOUD_SMS_TEMPLATE_CODE"]
    send_sms_request.phone_numbers = mobile
    send_sms_request.template_param = '{"code":"' + check_code + '"}'
    runtime = util_models.RuntimeOptions()
    try:
        res = client.send_sms_with_options(send_sms_request, runtime)
        return res
    except Exception as error:
        app.logger.error(error.message)
        app.logger.error(error.data.get("Recommend"))
        UtilClient.assert_as_string(error.message)
    return None
