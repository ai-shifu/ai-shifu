#  ilivedata
#  https://docs.ilivedata.com/textcheck/sync/check/

import datetime
import base64
import hmac
import json
from hashlib import sha256 as sha256
from urllib.request import Request, urlopen
from flask import Flask
from .dto import (
    CheckResultDTO,
    CHECK_RESULT_PASS,
    CHECK_RESULT_REVIEW,
    CHECK_RESULT_REJECT,
    CHECK_RESULT_UNKNOWN,
)


# pid = ""
# secret_key = b""
endpoint_host = "tsafe.ilivedata.com"
endpoint_path = "/api/v1/text/check"
endpoint_url = "https://tsafe.ilivedata.com/api/v1/text/check"

ILIVEDATA_RESULT_PASS = 0
ILIVEDATA_RESULT_REVIEW = 1
ILIVEDATA_RESULT_REJECT = 2


RESULT_MAP = {
    ILIVEDATA_RESULT_PASS: CHECK_RESULT_PASS,
    ILIVEDATA_RESULT_REVIEW: CHECK_RESULT_REVIEW,
    ILIVEDATA_RESULT_REJECT: CHECK_RESULT_REJECT,
}


PROVIDER = "ilivedata"
RISK_LABELS = {
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


def ilivedata_check(
    app: Flask, data_id: str, text: str, user_id: str
) -> CheckResultDTO:
    pid = app.config.get("ILIVEDATA_PID")
    secret_key = app.config.get("ILIVEDATA_SECRET_KEY").encode("utf-8")
    if not pid or not secret_key:
        app.logger.warning("ilivedata pid or secret_key is not set")
        return CheckResultDTO(
            check_result=CHECK_RESULT_UNKNOWN,
            risk_labels=[],
            risk_label_ids=[],
            provider=PROVIDER,
            raw_data={},
        )

    now_date = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"content": text, "userId": user_id, "sessionId": data_id}
    query_body = json.dumps(params)
    parameter = "POST\n"
    parameter += endpoint_host + "\n"
    parameter += endpoint_path + "\n"
    parameter += sha256(query_body.encode("utf-8")).hexdigest() + "\n"
    parameter += "X-AppId:" + pid + "\n"
    parameter += "X-TimeStamp:" + now_date
    signature = base64.b64encode(
        hmac.new(secret_key, parameter.encode("utf-8"), digestmod=sha256).digest()
    )
    ret = send(query_body, signature, now_date, pid)

    if ret.get("errorCode") == 0:
        return CheckResultDTO(
            check_result=RESULT_MAP.get(
                ret.get("textSpam", {}).get("result", ILIVEDATA_RESULT_PASS)
            ),
            risk_labels=[
                tag_infos.get("tagName", "")
                for tag_infos in ret.get("textSpam", {}).get("tags", [])
            ],
            risk_label_ids=[
                tag_infos.get("tag", "")
                for tag_infos in ret.get("textSpam", {}).get("tags", [])
            ],
            provider=PROVIDER,
            raw_data=ret,
        )
    else:
        app.logger.error(f"ilivedata check error: {ret.get('errorCode')}")
        return CheckResultDTO(
            check_result=CHECK_RESULT_UNKNOWN,
            risk_labels=[],
            risk_label_ids=[],
            provider=PROVIDER,
            raw_data=ret,
        )


def send(querystring, signature, time_stamp, pid):
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
