from flaskr.service.common import ERROR_CODE, AppException


class PaidException(AppException):
    def __init__(self):
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


class BreakException(AppException):
    def __init__(self):
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )
