# ruff: noqa: INP001 - The harness mounts this standalone WSGI entry by file.
"""Keep runtime-harness SMS delivery local without replacing business APIs."""

from alibabacloud_dysmsapi20170525 import models as sms_models
from flaskr.api.sms import aliyun as sms_aliyun


def _accept_sms(
    _client: object, _request: object, _runtime: object
) -> sms_models.SendSmsResponse:
    """Stand in only for the SMS supplier transport in the isolated harness."""
    return sms_models.SendSmsResponse(body=sms_models.SendSmsResponseBody(code="OK"))


# This file is mounted read-only outside /app only by the runtime harness.
# Production images and ordinary development startup never import it.
sms_aliyun.Dysmsapi20170525Client.send_sms_with_options = _accept_sms

from development_app import app  # noqa: E402, F401 - install transport before app startup
