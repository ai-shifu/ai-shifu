from flaskr.service.common import AppException, ERROR_CODE


class PaidException(AppException):
    def __init__(self):
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["module.backend.common.unknownError"],
            ),
        )
