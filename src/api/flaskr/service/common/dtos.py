"""Define DTOs for shared backend behavior."""

import math

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, Field

USER_STATE_UNREGISTERED = 0
USER_STATE_REGISTERED = 1
USER_STATE_TRAIL = 2
USER_STATE_PAID = 3


USE_STATE_VALUES = {
    USER_STATE_UNREGISTERED: "未注册",
    USER_STATE_REGISTERED: "已注册",
    USER_STATE_TRAIL: "试用",
    USER_STATE_PAID: "已付费",
}


@register_schema_to_swagger
class UserInfo:
    """Represent user identity details in API responses."""

    user_id: str
    username: str
    name: str
    email: str
    mobile: str
    user_state: str
    language: str
    user_avatar: str
    is_creator: bool
    is_operator: bool

    def __init__(
        self,
        user_id: object,
        username: object,
        name: object,
        email: object,
        mobile: object,
        user_state: object,
        wx_openid: object,
        language: object,
        user_avatar: object | None = None,
        is_creator: bool = False,
        is_operator: bool = False,
    ) -> None:
        """Build a serialized user-information payload."""
        self.user_id = user_id
        self.username = username
        self.name = name
        self.email = email
        self.mobile = mobile
        self.user_state = USE_STATE_VALUES.get(
            user_state, USE_STATE_VALUES[USER_STATE_UNREGISTERED]
        )
        self.wx_openid = wx_openid
        self.language = language
        self.user_avatar = user_avatar
        self.is_creator = is_creator
        self.is_operator = is_operator

    def __json__(self) -> dict:
        """Return the user information as JSON-compatible data."""
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
            "is_creator": self.is_creator,
            "is_operator": self.is_operator,
        }

    def __html__(self) -> dict:
        """Return the serialized user-information payload."""
        return self.__json__()


@register_schema_to_swagger
class UserToken:
    """Represent an issued user token in API responses."""

    userInfo: UserInfo  # noqa: N815 - exact serialized and Swagger field name
    token: str

    def __init__(self, user_info: UserInfo, token: object) -> None:
        """Pair serialized user information with its access token."""
        self.userInfo = user_info
        self.token = token

    def __json__(self) -> dict:
        """Return the user token as JSON-compatible data."""
        return {
            "userInfo": self.userInfo,
            "token": self.token,
        }


@register_schema_to_swagger
class OAuthStartDTO:
    """Represent the API payload that starts an OAuth flow."""

    authorization_url: str
    state: str

    def __init__(self, authorization_url: str, state: str) -> None:
        """Build an OAuth authorization-start payload."""
        self.authorization_url = authorization_url
        self.state = state

    def __json__(self) -> dict:
        """Return the OAuth start response as JSON-compatible data."""
        return {
            "authorization_url": self.authorization_url,
            "state": self.state,
        }


@register_schema_to_swagger
class PageNationDTO(BaseModel):
    """Represent pagination metadata in API responses."""

    page: int = Field(..., description="page")
    page_size: int = Field(..., description="page_size")
    total: int = Field(..., description="total")
    page_count: int = Field(..., description="page_count")
    data: list = Field(..., description="data")

    def __init__(self, page: int, page_size: int, total: int, data: object) -> None:
        """Build a paginated response payload."""
        super().__init__(
            page=page,
            page_count=math.ceil(total / page_size if page_size > 0 else 0),
            page_size=page_size,
            total=total,
            data=data,
        )
        self.page = page
        self.page_size = page_size
        self.total = total
        self.page_count = math.ceil(total / page_size if page_size > 0 else 0)
        self.data = data

    def __json__(self) -> dict:
        """Return the paginated response as JSON-compatible data."""
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count": self.page_count,
            "items": self.data,
        }
