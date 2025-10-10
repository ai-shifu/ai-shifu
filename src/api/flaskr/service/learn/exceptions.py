from flaskr.service.common import AppException, ERROR_CODE


class PaidException(AppException):
    def __init__(self):
        super().__init__(
            "ORDER.COURSE_NOT_PAID",
            ERROR_CODE.get("ORDER.COURSE_NOT_PAID", ERROR_CODE["COMMON.UNKNOWN_ERROR"]),
        )
