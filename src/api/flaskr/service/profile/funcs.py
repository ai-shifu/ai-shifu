from flask import Flask

from .models import UserProfile
from ...dao import db
from ..user.models import User

class UserProfileDTO:
    def __init__(self, user_id, profile_key, profile_value, profile_type):
        self.user_id = user_id
        self.profile_key = profile_key
        self.profile_value = profile_value
        self.profile_type = profile_type

    def __json__(self):
        return {
            "user_id": self.user_id,
            "profile_key": self.profile_key,
            "profile_value": self.profile_value,
            "profile_type": self.profile_type
        }



PROFILES_LABLES = {
    "nickname":{
        "label":"昵称",
        "mapping":"name"
    },
    "sex":{
        "label":"性别",
        "mapping":"user_sex",
        "items":["不告诉","男","女"],
        "items_mapping":{
            "不告诉":0,
            "男":1,
            "女":2
        }
    },
    "birth":{
        "label":"生日",
        "mapping":"user_birth",
        "type":"date"
    },
    "avatar":{
        "label":"头像",
        "mapping":"user_avatar",
        "type":"image"
    },
    "industry":{
        "label":"行业"
    },
    "occupation":{
        "label":"职业",
    },
    "ai_tools":{
        "label":"编程工具",
        "items":[ "GitHub Copilot","通义灵码"]
    },
    "style":{
        "label":"授课风格",
        "items":[]
    },
    "programming":{
        "label": "编程熟悉程度",
        "items":[
            "完全没接触过",
            "学过但还无法编写程序",
            "会1门及以上语言"
        ]
    },
    "user_os":{
        "lable":"用户操作系统",
    }
}


def get_user_profile_by_user_id(app:Flask,user_id:str, profile_key:str)->UserProfileDTO:
    user_profile = UserProfile.query.filter_by(user_id=user_id, profile_key=profile_key).first()
    if user_profile:
        return UserProfileDTO(user_profile.user_id, user_profile.profile_key, user_profile.profile_value, user_profile.profile_type)
    return None

def save_user_profile(app:Flask, user_id:str, profile_key:str, profile_value:str, profile_type:int):
    with app.app_context():
        user_profile = UserProfile.query.filter_by(user_id=user_id, profile_key=profile_key).first()
        if user_profile:
            user_profile.profile_value = profile_value
            user_profile.profile_type = profile_type
        else:
            user_profile = UserProfile(user_id=user_id, profile_key=profile_key, profile_value=profile_value, profile_type=profile_type)
            db.session.add(user_profile)
        db.session.commit()
        return UserProfileDTO(user_profile.user_id, user_profile.profile_key, user_profile.profile_value, user_profile.profile_type)

def save_user_profiles(app:Flask,user_id:str, profiles:dict):
    with app.app_context():
        app.logger.info("select user profiles:{}".format(profiles))
        for key, value in profiles.items():
            user_profile = UserProfile.query.filter_by(user_id=user_id, profile_key=key).first()
            if user_profile:
                user_profile.profile_value = value
            else:
                user_profile = UserProfile(user_id=user_id, profile_key=key, profile_value=value, profile_type=1)
                db.session.add(user_profile)
        db.session.commit()
        return True
def get_user_profiles(app:Flask,user_id:str,keys:list=None)->dict:
    user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
    result = {}
    if keys is None:
        for user_profile in user_profiles:
            result[user_profile.profile_key] = user_profile.profile_value
        return result
    for user_profile in user_profiles:
        if user_profile.profile_key in keys:
            result[user_profile.profile_key] = user_profile.profile_value
    return result





def get_user_profile_labels(app:Flask,user_id:str):
    user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
    user_info = User.query.filter(User.user_id==user_id).first()
    result = {}
    if user_info:
        for key in PROFILES_LABLES:
            print(key)
            if PROFILES_LABLES[key].get("mapping"):
                result[key] ={
                    # "key": key,
                    "label": PROFILES_LABLES[key]["label"],
                    "type":  PROFILES_LABLES[key].get("type", "select" if "items" in PROFILES_LABLES[key]  else "text"),
                    "value": getattr(user_info, PROFILES_LABLES[key]["mapping"]),
                    "items": PROFILES_LABLES[key].get("items")
                }
                if PROFILES_LABLES[key].get("items_mapping"):
                    result[key]["value"] = PROFILES_LABLES[key]["items"][getattr(user_info, PROFILES_LABLES[key]["mapping"])]

    for user_profile in user_profiles:
        if user_profile.profile_key in PROFILES_LABLES:
            if result.get(user_profile.profile_key) is None:
                result[user_profile.profile_key]={ 
                    # "key": user_profile.profile_key,
                    "label": PROFILES_LABLES[user_profile.profile_key]["label"],
                    "type":  PROFILES_LABLES[key].get("type", "select" if "items" in PROFILES_LABLES[user_profile.profile_key]  else "text"),
                    "value": user_profile.profile_value,
                    "items":PROFILES_LABLES[user_profile.profile_key]["items"] if "items" in PROFILES_LABLES[user_profile.profile_key] else None
                }
                if PROFILES_LABLES[user_profile.profile_key].get("items_mapping"):
                    result[key]["value"] = PROFILES_LABLES[key]["items"][ user_profile.profile_value]
            else:
                result[user_profile.profile_key]["value"] = user_profile.profile_value
     
                
    return result