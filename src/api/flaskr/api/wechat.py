"""Integrate WeChat APIs and OAuth flows."""

import requests
from flask import Flask

from flaskr.service.config import get_config


class WeChatAPIError(RuntimeError):
    """Report a WeChat transport failure without exposing request secrets."""

    def __init__(self) -> None:
        """Create a stable exception whose text contains no request data."""
        super().__init__("WeChat OAuth request failed")


def get_wechat_access_token(app: Flask, code: str) -> dict[str, object] | None:
    """Return wechat access token."""
    app.logger.info("get_wechat_access_token")
    app_id = app.config.get("WECHAT_APP_ID") or get_config("WECHAT_APP_ID", "")
    app_secret = app.config.get("WECHAT_APP_SECRET") or get_config(
        "WECHAT_APP_SECRET", ""
    )
    url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={app_id}&secret={app_secret}&code={code}&grant_type=authorization_code"
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        raise WeChatAPIError from None
    if response.status_code == 200:
        app.logger.info("auth_event=wechat_access_token_exchange_succeeded")
        return response.json()
    app.logger.warning(
        "auth_event=wechat_access_token_exchange_rejected status_code=%s",
        response.status_code,
    )
    return None
