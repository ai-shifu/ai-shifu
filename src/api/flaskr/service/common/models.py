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
    "module.backend.user.userNotFound": 1001,
    "module.backend.user.userAlreadyExists": 1002,
    "module.backend.user.userNotLogin": 1004,
    "module.backend.user.userTokenExpired": 1005,
    "module.backend.user.checkCodeError": 1009,
    "module.backend.user.checkCodeExpired": 1010,
    "module.backend.user.smsSendError": 1011,
    "module.backend.user.smsSendFrequently": 1012,
    "module.backend.user.smsSendExpired": 1013,
    "module.backend.user.smsCheckError": 1014,
    "module.backend.common.unknownError": 9999,
    # order error
    "module.backend.order.orderNotFound": 3001,
    "module.backend.order.orderAlreadyExists": 3002,
    "module.backend.order.orderStatusError": 3003,
    "module.backend.order.orderPayError": 3004,
    "module.backend.order.orderRefundError": 3005,
    "module.backend.order.orderPayExpired": 3006,
    "module.backend.order.orderPayNotFound": 3007,
    "module.backend.order.orderHasPaid": 3008,
    # discount error
    "module.backend.discount.discountNotFound": 3101,
    "module.backend.discount.discountAlreadyUsed": 3102,
    "module.backend.discount.discountLimit": 3103,
    "module.backend.discount.discountNotStart": 3104,
    "module.backend.discount.discountExpired": 3105,
    "module.backend.discount.orderDiscountAlreadyUsed": 3106,
    "module.backend.discount.discountLimitExceeded": 3107,
    "module.backend.discount.discountAlreadyExpired": 3108,
    "module.backend.discount.discountCountNotZero": 3109,
    # course error
    "module.backend.course.courseNotFound": 4001,
    "module.backend.course.lessonCannotBeReset": 4002,
    "module.backend.course.lessonNotFound": 4003,
    "module.backend.course.lessonNotFoundInCourse": 4004,
    # pay error
    "module.backend.pay.payChannelNotSupport": 5001,
    # file error
    "module.backend.file.fileUploadError": 6001,
    "module.backend.file.fileTypeNotSupport": 6002,
    "module.backend.file.fileSizeExceed": 6003,
    "module.backend.file.videoInvalidBilibiliLink": 6004,
    "module.backend.file.videoBilibiliApiError": 6005,
    "module.backend.file.videoBilibiliApiRequestFailed": 6006,
    "module.backend.file.videoUnsupportedVideoSite": 6007,
    "module.backend.file.videoGetInfoError": 6008,
    # params error
    "module.backend.common.paramsError": 2001,
    "module.backend.common.textNotAllowed": 2002,
    # Admin errors
    "module.backend.admin.viewNotFound": 7001,
    # LLM errors
    "module.backend.llm.noDefaultLlm": 8001,
    "module.backend.llm.specifiedLlmNotConfigured": 8002,
    "module.backend.llm.modelNotSupported": 8003,
    # api errors
    "module.backend.api.alibabaCloudNotConfigured": 9001,
    "module.backend.scenario.noPermission": 9002,
    # Unauthorized
    "module.backend.shifu.noPermission": 401,
}


def register_error(error_name, error_code):
    ERROR_CODE[error_name] = error_code


def raise_param_error(param_message):
    raise AppException(
        _("module.backend.common.paramsError").format(param_message=param_message),
        ERROR_CODE["module.backend.common.paramsError"],
    )


def raise_error(error_name):
    raise AppException(
        _(error_name),
        ERROR_CODE.get(error_name, ERROR_CODE["module.backend.common.unknownError"]),
    )


def raise_error_with_args(error_name, **kwargs):
    raise AppException(
        _(error_name).format(**kwargs),
        ERROR_CODE.get(error_name, ERROR_CODE["module.backend.common.unknownError"]),
    )


def reg_error_code(error_name, error_code):
    ERROR_CODE[error_name] = error_code
