def test_learn_api(app):
    from flaskr.service.learn.learn_funcs import get_shifu_info
    from flaskr.service.shifu.models import PublishedShifu
    from flaskr.route.common import make_common_response

    with app.app_context():
        lesson = PublishedShifu.query.first()
        lesson_id = lesson.shifu_bid
        res = make_common_response(get_shifu_info(app, lesson_id, False))
        app.logger.info(res)
        print(res)


def test_learn_api_outline_item_tree(app):
    from flaskr.service.learn.learn_funcs import get_outline_item_tree
    from flaskr.service.shifu.models import PublishedShifu
    from flaskr.route.common import make_common_response
    from flaskr.service.user.models import User

    with app.app_context():
        lesson = (
            PublishedShifu.query.filter(PublishedShifu.deleted == 0)
            .order_by(PublishedShifu.id.desc())
            .first()
        )
        print(lesson.title)
        user = User.query.first()
        user_id = user.user_id
        res = make_common_response(
            get_outline_item_tree(
                app, "cf2e89e4bb0048f9b010d4703c0cf826", user_id, False
            )
        )
        app.logger.info(res)
        print(res)
