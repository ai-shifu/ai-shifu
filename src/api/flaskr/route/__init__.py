from .common import register_common_handler
from .user import register_user_handler
from .course import register_course_handler
from .study import register_study_handler
from .dicts import register_dict_handler
from .order import register_order_handler
from .callback import register_callback_handler
from .test import register_test_routes


def register_route(app):
    prefix = app.config.get("PATH_PREFIX", "")
    app = register_common_handler(app)
    app = register_user_handler(app, prefix + "/user")
    app = register_course_handler(app, prefix + "/course")
    app = register_study_handler(app, prefix + "/study")
    app = register_dict_handler(app, prefix + "/dict")
    app = register_order_handler(app, prefix + "/order")
    app = register_callback_handler(app, prefix + "/callback")
    app = register_test_routes(app, prefix + "/test")
    return app
