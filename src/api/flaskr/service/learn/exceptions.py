"""Define domain exceptions for learning sessions."""

from flaskr.service.common import ERROR_CODE, AppError
from flaskr.util.deprecation import deprecated_alias_getattr


class PaidError(AppError):
    def __init__(self) -> None:
        """Initialize the paid-content control-flow signal."""
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


class BreakError(AppError):
    def __init__(self) -> None:
        """Initialize the run-break control-flow signal."""
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


__getattr__ = deprecated_alias_getattr(
    __name__, {"PaidException": "PaidError", "BreakException": "BreakError"}, globals()
)
