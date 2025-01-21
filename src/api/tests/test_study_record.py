def test_study_record(app):
    from flaskr.service.study import get_study_record

    with app.app_context():
        user_id = "076013a3d84544d58fbd367183857531"

        from flaskr.route.common import make_common_response

        res = get_study_record(
            app, user_id, lesson_id="4eb763e98ba140ffaae83eaa8e9ba198"
        )
        app.logger.info("res:{}".format(make_common_response(res)))
