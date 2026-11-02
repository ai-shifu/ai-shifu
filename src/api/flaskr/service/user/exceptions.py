"""Define domain exceptions for user accounts."""

from flaskr.i18n import _
from flaskr.service.common import ERROR_CODE, AppError


class UserNotLoginError(AppError):
    """Signal that an operation requires an authenticated user."""

    def __init__(self) -> None:
        """Initialize the unauthenticated-user error."""
        super().__init__(
            _("server.user.userNotLogin"),
            ERROR_CODE.get(
                "server.user.userNotLogin",
                ERROR_CODE["server.common.unknownError"],
            ),
        )
