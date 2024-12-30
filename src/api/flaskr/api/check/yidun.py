# netease yidun check
# ref: https://support.dun.163.com/documents/588434200783982592?docId=791131792583602176


import time
import hashlib
import random
from flask import Flask
from urllib.parse import urlencode
from gmssl import sm3, func
import requests
from flaskr.common.config import get_config
from .dto import (
    CheckResultDTO,
    CHECK_RESULT_PASS,
    CHECK_RESULT_REVIEW,
    CHECK_RESULT_REJECT,
    CHECK_RESULT_UNCONF,
    CHECK_RESULT_UNKNOWN,
)


URL = "http://as.dun.163.com/v5/text/check"


YIDUN_SECRET_ID = get_config("NETEASE_YIDUN_SECRET_ID")
YIDUN_SECRET_KEY = get_config("NETEASE_YIDUN_SECRET_KEY")
YIDUN_BUSINESS_ID = get_config("NETEASE_YIDUN_BUSINESS_ID")
VERSION = "v5.3"


YIDUN_RESULT_SUGGESTION_PASS = 0
YIDUN_RESULT_SUGGESTION_REVIEW = 1
YIDUN_RESULT_SUGGESTION_REJECT = 2


PROVIDER = "yidun"


RISK_LABLES = {
    100: "色情",
    200: "广告",
    260: "广告法",
    300: "暴恐",
    400: "违禁",
    500: "涉政",
    600: "谩骂",
    700: "灌水",
    900: "其他",
    1100: "涉价值观",
}


CHECK_RESULT_MAP = {
    YIDUN_RESULT_SUGGESTION_PASS: CHECK_RESULT_PASS,
    YIDUN_RESULT_SUGGESTION_REVIEW: CHECK_RESULT_REVIEW,
    YIDUN_RESULT_SUGGESTION_REJECT: CHECK_RESULT_REJECT,
}


def gen_signature(params=None):
    """生成签名信息
    Args:
        params (object) 请求参数
    Returns:
        参数签名md5值
    """
    buff = ""
    for k in sorted(params.keys()):
        buff += str(k) + str(params[k])
    buff += YIDUN_SECRET_KEY
    if "signatureMethod" in params.keys() and params["signatureMethod"] == "SM3":
        return sm3.sm3_hash(func.bytes_to_list(bytes(buff, encoding="utf8")))
    else:
        return hashlib.md5(buff.encode("utf8")).hexdigest()


def yidun_check(app: Flask, data_id: str, content: str, user_id: str = None):
    if not YIDUN_SECRET_ID or not YIDUN_SECRET_KEY or not YIDUN_BUSINESS_ID:
        app.logger.warning(
            "YIDUN_SECRET_ID, YIDUN_SECRET_KEY, YIDUN_BUSINESS_ID not configured"
        )
        return CheckResultDTO(
            check_result=CHECK_RESULT_UNCONF,
            risk_labels=[],
            risk_label_ids=[],
            provider=PROVIDER,
            raw_data={},
        )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    params = {}
    params["secretId"] = YIDUN_SECRET_ID
    params["content"] = content
    params["dataId"] = data_id
    params["businessId"] = YIDUN_BUSINESS_ID
    params["version"] = VERSION
    params["timestamp"] = int(time.time() * 1000)
    params["nonce"] = int(random.random() * 100000000)
    if user_id:
        params["account"] = user_id
    params["signature"] = gen_signature(params)

    try:
        params = urlencode(params).encode("utf8")
        response = requests.post(URL, data=params, headers=headers)
        response_json = response.json()
        if response_json.get("code", 200) == 200:
            return CheckResultDTO(
                check_result=CHECK_RESULT_MAP.get(
                    response_json.get("result", {})
                    .get("antispam", {})
                    .get("suggestion", YIDUN_RESULT_SUGGESTION_PASS)
                ),
                risk_labels=[
                    RISK_LABLES.get(
                        response_json.get("result", {})
                        .get("antispam", {})
                        .get("label", 100),
                        "",
                    )
                ],
                risk_label_ids=[
                    response_json.get("result", {})
                    .get("antispam", {})
                    .get("label", 100)
                ],
                provider=PROVIDER,
            )
        else:
            app.logger.error(f"yidun check error: {response_json.get('message', '')}")
            return CheckResultDTO(
                check_result=CHECK_RESULT_UNKNOWN,
                risk_labels=[],
                risk_label_ids=[],
                provider=PROVIDER,
                raw_data=response_json,
            )
    except Exception as ex:
        app.logger.error(f"yidun check error: {str(ex)}")
        return CheckResultDTO(
            check_result=CHECK_RESULT_UNKNOWN,
            risk_labels=[],
            risk_label_ids=[],
            provider=PROVIDER,
            raw_data={},
        )
