import time
import hashlib
import random
from flask import Flask
from urllib.parse import urlencode
from gmssl import sm3, func
import requests
from flaskr.common.config import get_config

URL = "http://as.dun.163.com/v5/text/check"


EDUN_SECRET_ID = get_config("NETEASE_YIDUN_SECRET_ID")
EDUN_SECRET_KEY = get_config("NETEASE_YIDUN_SECRET_KEY")
EDUN_BUSINESS_ID = get_config("NETEASE_YIDUN_BUSINESS_ID")
VERSION = "v5.3"


EDUN_RESULT_SUGGESTION_PASS = 0
EDUN_RESULT_SUGGESTION_REVIEW = 1
EDUN_RESULT_SUGGESTION_REJECT = 2


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
    buff += EDUN_SECRET_KEY
    if "signatureMethod" in params.keys() and params["signatureMethod"] == "SM3":
        return sm3.sm3_hash(func.bytes_to_list(bytes(buff, encoding="utf8")))
    else:
        return hashlib.md5(buff.encode("utf8")).hexdigest()


def check_text(app: Flask, data_id: str, content: str, user_id: str = None):
    if not EDUN_SECRET_ID or not EDUN_SECRET_KEY or not EDUN_BUSINESS_ID:
        app.logger.warning(
            "EDUN_SECRET_ID, EDUN_SECRET_KEY, EDUN_BUSINESS_ID not configured"
        )
        return {}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    params = {}
    params["secretId"] = EDUN_SECRET_ID
    params["content"] = content
    params["dataId"] = data_id
    params["businessId"] = EDUN_BUSINESS_ID
    params["version"] = VERSION
    params["timestamp"] = int(time.time() * 1000)
    params["nonce"] = int(random.random() * 100000000)
    if user_id:
        params["account"] = user_id
    # params["signatureMethod"] = "SM3"  # 签名方法，默认MD5，支持SM3
    params["signature"] = gen_signature(params)

    try:
        params = urlencode(params).encode("utf8")
        response = requests.post(URL, data=params, headers=headers)
        return response.json()
    except Exception as ex:
        print("调用API接口失败:", str(ex))
        return {}
