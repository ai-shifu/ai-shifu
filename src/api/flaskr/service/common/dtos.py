
from ...common.swagger import register_schema_to_swagger



USER_STATE_UNTEGISTERED = 0
USER_STATE_REGISTERED = 1
USER_STATE_TRAIL = 2
USER_STATE_PAID = 3


USE_STATE_VALUES = {
    USER_STATE_UNTEGISTERED: "未注册",
    USER_STATE_REGISTERED: "已注册",
    USER_STATE_TRAIL: "试用",
    USER_STATE_PAID: "已付费"
}

@register_schema_to_swagger
class UserInfo:
    user_id: str
    username: str
    name: str
    email: str
    mobile: str
    model: str
    user_state: str
    def __init__(self, user_id, username, name, email, mobile,model,user_state):
        self.user_id = user_id
        self.username = username
        self.name = name
        self.email = email
        self.mobile = mobile
        self.model = model
        self.user_state = USE_STATE_VALUES[user_state]
    def __json__(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "name": self.name,
            "email": self.email,
            "mobile": self.mobile,
            "state": self.user_state,
        }
    def __html__(self):
        return self.__json__()


@register_schema_to_swagger
class UserToken:
    userInfo: UserInfo
    token: str
    def __init__(self,userInfo:UserInfo, token):
        self.userInfo = userInfo
        self.token = token
    def __json__(self):
        return {
            "userInfo": self.userInfo,
            "token": self.token,
        }







@register_schema_to_swagger
class PageNationDTO:
    def __init__(self,page:int,page_size:int,total:int,data) -> None:
        self.page = page
        self.page_size = page_size
        self.total = total
        self.page_count = total//page_size + 1
        self.data = data
    def __json__(self):
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "page_count":self.page_count,
            "items":self.data
        }