# Desc: Common models for the application
from flaskr.i18n import _


class AppException(Exception):
    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        self.code = status_code
        self.payload = payload

    def __json__(self):
        rv = dict(self.payload or ())
        rv["message"] = self.message
        rv["code"] = self.code
        return rv

    def __str__(self):
        return self.message

    def __html__(self):
        return self.__json__()


ERROR_CODE = {
    "USER.USER_NOT_FOUND": 1001,
    "USER.USER_ALREADY_EXISTS": 1002,
    "USER.USER_PASSWORD_ERROR": 1003,
    "USER.USER_NOT_LOGIN": 1004,
    "USER.USER_TOKEN_EXPIRED": 1005,
    "USER.OLD_PASSWORD_ERROR": 1006,
    "USER.RESET_PWD_CODE_EXPIRED": 1007,
    "USER.RESET_PWD_CODE_ERROR": 1008,
    "USER.CHECK_CODE_ERROR": 1009,
    "USER.CHECK_CODE_EXPIRED": 1010,
    "USER.SMS_SEND_ERROR": 1011,
    "USER.SMS_SEND_FREQUENTLY": 1012,
    "USER.SMS_SEND_EXPIRED": 1013,
    "USER.SMS_CHECK_ERROR": 1014,
    "COMMON.UNKNOWN_ERROR": 9999,
    # order error
    "ORDER.ORDER_NOT_FOUND": 3001,
    "ORDER.ORDER_ALREADY_EXISTS": 3002,
    "ORDER.ORDER_STATUS_ERROR": 3003,
    "ORDER.ORDER_PAY_ERROR": 3004,
    "ORDER.ORDER_REFUND_ERROR": 3005,
    "ORDER.ORDER_PAY_EXPIRED": 3006,
    "ORDER.ORDER_PAY_NOT_FOUND": 3007,
    "ORDER.ORDER_HAS_PAID": 3008,
    # discount error
    "DISCOUNT.DISCOUNT_NOT_FOUND": 3101,
    "DISCOUNT.DISCOUNT_ALREADY_USED": 3102,
    "DISCOUNT.DISCOUNT_LIMIT": 3103,
    "DISCOUNT.DISCOUNT_NOT_START": 3104,
    "DISCOUNT.DISCOUNT_EXPIRED": 3105,
    "DISCOUNT.ORDER_DISCOUNT_ALREADY_USED": 3106,
    "DISCOUNT.DISCOUNT_LIMIT_EXCEEDED": 3107,
    "DISCOUNT.DISCOUNT_ALREADY_EXPIRED": 3108,
    "DISCOUNT.DISCOUNT_COUNT_NOT_ZERO": 3109,
    # course error
    "COURSE.COURSE_NOT_FOUND": 4001,
    "COURSE.LESSON_CANNOT_BE_RESET": 4002,
    "COURSE.LESSON_NOT_FOUND": 4003,
    "COURSE.LESSON_NOT_FOUND_IN_COURSE": 4004,
    # pay error
    "PAY.PAY_CHANNEL_NOT_SUPPORT": 5001,
    # file error
    "FILE.FILE_UPLOAD_ERROR": 6001,
    "FILE.FILE_TYPE_NOT_SUPPORT": 6002,
    "FILE.FILE_SIZE_EXCEED": 6003,
    # params error
    "COMMON.PARAMS_ERROR": 2001,
    "COMMON.TEXT_NOT_ALLOWED": 2002,
    # Admin errors
    "ADMIN.VIEW_NOT_FOUND": 7001,
    # LLM errors
    "LLM.NO_DEFAULT_LLM": 8001,
    "LLM.SPECIFIED_LLM_NOT_CONFIGURED": 8002,
    "LLM.MODEL_NOT_SUPPORTED": 8003,
    # api errors
    "API.ALIBABA_CLOUD_NOT_CONFIGURED": 9001,
}


def register_error(error_name, error_code):
    ERROR_CODE[error_name] = error_code


def raise_param_error(param_message):
    raise AppException(
        _("COMMON.PARAMS_ERROR").format(param_message=param_message),
        ERROR_CODE["COMMON.PARAMS_ERROR"],
    )


def raise_error(error_name):
    raise AppException(
        _(error_name),
        ERROR_CODE.get(error_name, ERROR_CODE["COMMON.UNKNOWN_ERROR"]),
    )


def raise_error_with_args(error_name, **kwargs):
    raise AppException(
        _(error_name).format(**kwargs),
        ERROR_CODE.get(error_name, ERROR_CODE["COMMON.UNKNOWN_ERROR"]),
    )


def reg_error_code(error_name, error_code):
    ERROR_CODE[error_name] = error_code
