from flask import Flask
import requests
import json
from flaskr.service.config import get_config

# feishu api
# ref: https://open.feishu.cn/document/server-docs/docs/docs-overview


def send_notify(app: Flask, title, msgs):
    url = get_config("FEISHU_NOTIFY_URL", None)
    if not url:
        app.logger.warning("feishu notify url not found")
        return
    headers = {"Content-Type": "application/json"}
    data = {
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": "师傅~" + title, "content": []}}},
    }

    for msg in msgs:
        data["content"]["post"]["zh_cn"]["content"].append(
            [{"tag": "text", "text": msg}]
        )

    try:
        response = requests.post(
            url, headers=headers, data=json.dumps(data), timeout=10
        )
    except requests.RequestException:
        app.logger.exception("send_notify request failed")
        return None

    response_text = response.text or ""
    if response.status_code < 200 or response.status_code >= 300:
        app.logger.warning(
            "send_notify failed: status_code=%s response=%s",
            response.status_code,
            response_text[:1000],
        )
        return None

    try:
        result = response.json()
    except ValueError:
        result = {"status_code": response.status_code, "text": response_text[:1000]}

    app.logger.info("send_notify:%s", result)
    return result
