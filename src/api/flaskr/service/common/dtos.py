from ...common.swagger import register_schema_to_swagger
import math

USER_STATE_UNTEGISTERED = 0
USER_STATE_REGISTERED = 1
USER_STATE_TRAIL = 2
USER_STATE_PAID = 3


USE_STATE_VALUES = {
    USER_STATE_UNTEGISTERED: "未注册",
    USER_STATE_REGISTERED: "已注册",
    USER_STATE_TRAIL: "试用",
    USER_STATE_PAID: "已付费",
}


@register_schema_to_swagger
class UserInfo:
    user_id: str
    username: str
    name: str
    email: str
    mobile: str
    user_state: str
    language: str
    user_avatar: str
    has_password: bool

    def __init__(
        self,
        user_id,
        username,
        name,
        email,
        mobile,
        user_state,
        wx_openid,
        language,
        has_password,
        user_avatar=None,
    ):
        self.user_id = user_id
        self.username = username
        self.name = name
        self.email = email
        self.mobile = mobile
        self.user_state = USE_STATE_VALUES[user_state]
        self.wx_openid = wx_openid
        self.language = language
        self.user_avatar = user_avatar
        self.has_password = has_password

    def __json__(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "name": self.name,
            "email": self.email,
            "mobile": self.mobile,
            "state": self.user_state,
            "openid": self.wx_openid,
            "language": self.language,
            "avatar": self.user_avatar,
            "has_password": self.has_password,
        }

    def __html__(self):
        return self.__json__()


@register_schema_to_swagger
class UserToken:
    userInfo: UserInfo
    token: str

    def __init__(self, userInfo: UserInfo, token):
        self.userInfo = userInfo
        self.token = token

    def __json__(self):
        return {
            "userInfo": self.userInfo,
            "token": self.token,
        }


@register_schema_to_swagger
class PageNationDTO:
    def __init__(self, page: int, page_size: int, total: int, data) -> None:
        self.page = page
        self.page_size = page_size
        self.total = total
        self.page_count = math.ceil(total / page_size)
        self.data = data

    def __json__(self):
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
            "items": self.data,
        }
