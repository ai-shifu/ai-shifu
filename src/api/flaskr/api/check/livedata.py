#  ilivedata
#  https://docs.ilivedata.com/textcheck/sync/check/

import datetime
import base64
import hmac
import json
from hashlib import sha256 as sha256
from urllib.request import Request, urlopen
from flask import Flask


pid = ""
secret_key = b""
endpoint_host = "tsafe.ilivedata.com"
endpoint_path = "/api/v1/text/check"
endpoint_url = "https://tsafe.ilivedata.com/api/v1/text/check"

LIVEDATA_RESULT_PASS = 0
LIVEDATA_RESULT_REVIEW = 1
LIVEDATA_RESULT_REJECT = 2

RISK_LABLES = {
    100: "涉政",
    110: "暴恐",
    120: "违禁",
    130: "色情",
    150: "广告",
    160: "辱骂",
    170: "仇恨言论",
    180: "未成年保护",
    190: "敏感热点",
    410: "违规表情",
    420: "昵称",
    300: "广告法",
    220: "私人交易",
    900: "其他",
    999: "用户自定义类",
}


def check(app: Flask, data_id: str, text: str, user_id: str):
    now_date = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {"content": text, "userId": user_id, "sessionId": data_id}
    query_body = json.dumps(params)
    print(query_body)
    parameter = "POST\n"
    parameter += endpoint_host + "\n"
    parameter += endpoint_path + "\n"
    parameter += sha256(query_body.encode("utf-8")).hexdigest() + "\n"
    parameter += "X-AppId:" + pid + "\n"
    parameter += "X-TimeStamp:" + now_date
    signature = base64.b64encode(
        hmac.new(secret_key, parameter.encode("utf-8"), digestmod=sha256).digest()
    )
    return send(query_body, signature, now_date)


def send(querystring, signature, time_stamp):
    headers = {
        "X-AppId": pid,
        "X-TimeStamp": time_stamp,
        "Content-type": "application/json",
        "Authorization": signature,
        "Host": endpoint_host,
        "Connection": "keep-alive",
    }

    req = Request(
        endpoint_url, querystring.encode("utf-8"), headers=headers, method="POST"
    )
    return json.loads(urlopen(req).read().decode(), strict=False)
