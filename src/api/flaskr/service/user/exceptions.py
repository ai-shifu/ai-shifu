from flaskr.service.common import AppException, ERROR_CODE


class UserNotLoginException(AppException):
    def __init__(self):
        super().__init__(
            "USER.USER_NOT_LOGIN",
            ERROR_CODE.get("USER.USER_NOT_LOGIN", ERROR_CODE["COMMON.UNKNOWN_ERROR"]),
        )
