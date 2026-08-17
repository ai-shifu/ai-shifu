from flaskr.i18n import _
from flaskr.service.common import ERROR_CODE, AppException


class UserNotLoginException(AppException):
    def __init__(self):
        super().__init__(
            _("server.user.userNotLogin"),
            ERROR_CODE.get(
                "server.user.userNotLogin",
                ERROR_CODE["server.common.unknownError"],
            ),
        )
