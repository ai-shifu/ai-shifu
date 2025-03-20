def test_study_progress(app):
    from flaskr.service.study.progress import get_course_info

    with app.app_context():
        print(get_course_info("be82ba87b2eb449a91fb2194dbfb2bc1"))
