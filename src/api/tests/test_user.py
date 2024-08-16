import pytest
import json

from tests.common import print_json
def test_get_user_profile(app):


    from flaskr.service.profile.funcs import get_user_profile_labels
    from flaskr.service.profile.funcs import update_user_profile
    with app.app_context():
        resp =  get_user_profile_labels(app,"42e03ab0a33d4904bf84793d5fc1f71b")
        print_json(resp)

        for item in resp:
            if item["label"] == "性别":
                item["value"] = "男"
                update_user_profile(app,"42e03ab0a33d4904bf84793d5fc1f71b",resp)
            if item['label'] == "用户操作系统":
                item["value"] = "MacOS"
                update_user_profile(app,"42e03ab0a33d4904bf84793d5fc1f71b",resp)
        print_json(resp)


import random

# def test_admin_create_new_user(app):
#     from flaskr.service.user import create_new_user
#     test_user_name = "test_user" + str(random.randint(1,100000))
#     user_token = create_new_user(app, test_user_name,test_user_name,test_user_name,test_user_name,test_user_name)
#     assert user_token is not None
#     assert len(user_token.token) > 0
#     print(user_token)
#     pass 