from flaskr.service.common import ERROR_CODE, AppError


class PaidError(AppError):
    def __init__(self):
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


class BreakError(AppError):
    def __init__(self):
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )
