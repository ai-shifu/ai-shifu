def test_get_study_record(app):
    from flaskr.service.study import get_study_record

    user_id = "4107339b74b0414fa0e5b7b64d68a2ae"
    lesson_id = "5071e9aa8d1246b5870c7970b679b7d4"
    study_record = get_study_record(app, user_id, lesson_id)
    assert study_record is not None
    # assert len(study_record) > 0
    app.logger.info(study_record.ui.lesson_id)
    print(study_record.ui.lesson_id)
    print([i.lesson_id for i in study_record.records])
    pass
