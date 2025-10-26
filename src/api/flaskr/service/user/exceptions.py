from flaskr.service.common import AppException, ERROR_CODE
from flaskr.i18n import _


class UserNotLoginException(AppException):
    def __init__(self):
        super().__init__(
            _("server.user.userNotLogin"),
            ERROR_CODE.get(
                "server.user.userNotLogin",
                ERROR_CODE["server.common.unknownError"],
            ),
        )
