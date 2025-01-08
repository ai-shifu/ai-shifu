def test_edun(app):
    from api.flaskr.api.check.yidun import check_text
    from flaskr.util.uuid import generate_id

    with app.app_context():
        edun = check_text(generate_id(app), generate_id(app), "你好啊")
        app.logger.info(edun)
