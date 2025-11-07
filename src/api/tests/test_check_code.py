def test_check_code(app):
    with app.app_context():
        from flaskr.service.user.common import verify_sms_code_without_phone

        user_id = "ab769989275a4eddbdf589558b9df089"
        chk = "0615"
        verify_sms_code_without_phone(app, user_id, chk)
