"""Route package entrypoints."""


def register_route(app):
    from .callback import register_callback_handler
    from .common import register_common_handler
    from .config import register_config_handler
    from .dicts import register_dict_handler
    from .open_api import register_open_api_handler
    from .order import register_order_handler
    from .storage import register_storage_handler
    from .user import register_user_handler

    prefix = app.config.get("PATH_PREFIX", "")
    app = register_common_handler(app)
    app = register_config_handler(app, prefix)
    app = register_storage_handler(app, prefix)
    app = register_user_handler(app, prefix + "/user")
    app = register_dict_handler(app, prefix + "/dict")
    app = register_order_handler(app, prefix + "/order")
    app = register_callback_handler(app, prefix + "/callback")
    app = register_open_api_handler(app, prefix + "/open-api/v1")
    return app
