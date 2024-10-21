def test_sms(app):
    from flaskr.service.user.funs import send_sms_code_without_check

    with app.app_context():
        phone = "18612312326"
        send_sms_code_without_check(
            app, "a0879d07bc2340238d1a5321e666a0a2", phone=phone
        )
