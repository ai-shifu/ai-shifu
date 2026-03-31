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

    r = requests.post(url, headers=headers, data=json.dumps(data))
    app.logger.info("send_notify:" + str(r.json()))
    return r.json()
