from .common import register_common_handler
from .user import register_user_handler
from .lesson import register_lesson_handler
from .course import register_course_handler
from .study import register_study_handler
from .dicts import register_dict_handler
from .tools import register_tools_handler
from .order import register_order_handler
from .callback import register_callback_handler
from .test import register_test_routes


def register_route(app):
    prefix = app.config.get("PATH_PREFIX", "")
    app = register_common_handler(app)
    app = register_user_handler(app, prefix + "/user")
    app = register_lesson_handler(app, prefix + "/lesson")
    app = register_course_handler(app, prefix + "/course")
    app = register_study_handler(app, prefix + "/study")
    app = register_dict_handler(app, prefix + "/dict")
    app = register_tools_handler(app, prefix + "/tools")
    app = register_order_handler(app, prefix + "/order")
    app = register_callback_handler(app, prefix + "/callback")
    app = register_test_routes(app, prefix + "/test")

    mode = app.config.get("MODE", "api")
    app.logger.info("current run mode:{}".format(mode))

    # if app.config.get("MODE", "api") == "admin":
    #     app.logger.info("current mode is admin register admin api")
    #     from .admin.user import register_user_route

    #     app = register_user_route(app, prefix + "/user")
    #     # register manager
    #     from .admin.manager import register_data_manager_route

    #     app = register_data_manager_route(app, prefix + "/manager")
    #     from .admin.tools import register_manager_tools_handler

    #     app = register_manager_tools_handler(app, prefix + "/tools")

    return app
