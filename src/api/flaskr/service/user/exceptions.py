from flaskr.i18n import _
from flaskr.service.common import ERROR_CODE, AppError
from flaskr.util.deprecation import deprecated_alias_getattr


class UserNotLoginError(AppError):
    def __init__(self) -> None:
        super().__init__(
            _("server.user.userNotLogin"),
            ERROR_CODE.get(
                "server.user.userNotLogin",
                ERROR_CODE["server.common.unknownError"],
            ),
        )


__getattr__ = deprecated_alias_getattr(
    __name__, {"UserNotLoginException": "UserNotLoginError"}, globals()
)
