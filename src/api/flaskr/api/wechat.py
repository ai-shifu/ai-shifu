from flask import Flask

import requests
from flaskr.service.config import get_config


def get_wechat_access_token(app: Flask, code: str):
    app.logger.info("get_wechat_access_token")
    app_id = get_config("WECHAT_APP_ID", "")
    app_secret = get_config("WECHAT_APP_SECRET", "")
    url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={app_id}&secret={app_secret}&code={code}&grant_type=authorization_code"
    response = requests.get(url)
    app.logger.info(f"get_wechat_access_token response: {response}")
    if response.status_code == 200:
        app.logger.info("get_wechat_access_token:" + str(response.json()))
        return response.json()
    return None
