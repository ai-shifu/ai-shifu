from flask import Flask
from .models import User


from api.flaskr.common.swagger import register_schema_to_swagger



@register_schema_to_swagger
class UserItemDTO:
    def __init__(self,user_id:str,mobile:str,nickname:str,sex:int,birth:Date) -> None:
        self.user_id = user_id
        self.mobile = mobile
        self.nickname = nickname
        self.sex = sex
        self.birth = birth.strftime("%Y-%m-%d")
    def __json__(self):
        return {
            "user_id": self.user_id,
            "mobile": self.mobile,
            "nickname": self.nickname,
            "sex":self.sex,
            "birth":self.birth
        }

    



def get_user_list(app:Flask,page:int=1,page_size:int=20,query=None):
    with app.app_context():
        app.logger.info("query:"+str(query)+" page:"+str(page)+" page_size:"+str(page_size))
        db_query = User.query
        if query:
            if query.get("mobile"):
                db_query = db_query.filter(User.mobile.like("%"+query.get("mobile")+"%"))
            if query.get("nickname"):
                db_query = db_query.filter(User.username.like("%"+query.get("nickname")+"%"))
            if query.get("user_id"):
                db_query = db_query.filter(User.user_id == query.get("user_id"))
        count = db_query.count()
        if count == 0:
            return {}
        users = db_query.order_by(User.created.desc()).offset((page-1)*page_size).limit(page_size)
        items =  [UserItemDTO(user.user_id,user.mobile,user.username,user.user_sex,user.user_birth) for user in users]
        return PageNationDTO(page,page_size,count,items)