"""Define domain exceptions for learning sessions."""

from flaskr.service.common import ERROR_CODE, AppError
from flaskr.util.deprecation import deprecated_alias_getattr


class PaidError(AppError):
    """Signal that the requested learning content requires payment."""

    def __init__(self: object) -> None:
        """Initialize the paid-content control-flow signal."""
        super().__init__(
            "server.order.courseNotPaid",
            ERROR_CODE.get(
                "server.order.courseNotPaid",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


class BreakError(AppError):
    """Signal that the current learning run should stop normally."""

    def __init__(self: object) -> None:
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
