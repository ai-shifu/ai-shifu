import pytest
import json

from tests.common import print_json
def test_get_user_profile(app):


    from flaskr.service.profile.funcs import get_user_profile_labels

    resp =  get_user_profile_labels(app,"49037a81b0a54ac8a9c823bbec23f0e3")
    print_json(resp)


import random

def test_admin_create_new_user(app):
    from flaskr.service.user import create_new_user
    test_user_name = "test_user" + str(random.randint(1,100000))
    user_token = create_new_user(app, test_user_name,test_user_name,test_user_name,test_user_name,test_user_name)
    assert user_token is not None
    assert len(user_token.token) > 0
    print(user_token)
    pass 