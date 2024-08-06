import random

def test_admin_create_new_user(app):
    from flaskr.service.admin import create_new_user
    test_user_name = "test_user" + str(random.randint(1,100000))
    user_token = create_new_user(app, test_user_name,test_user_name,test_user_name,test_user_name,test_user_name)
    assert user_token is not None
    assert len(user_token.token) > 0
    print(user_token)
    pass