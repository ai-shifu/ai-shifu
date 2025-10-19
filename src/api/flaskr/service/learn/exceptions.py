from flaskr.service.common import AppException, ERROR_CODE


class PaidException(AppException):
    def __init__(self):
        super().__init__(
            "module.backend.order.courseNotPaid",
            ERROR_CODE.get(
                "module.backend.order.courseNotPaid",
                ERROR_CODE["module.backend.common.unknownError"],
            ),
        )
