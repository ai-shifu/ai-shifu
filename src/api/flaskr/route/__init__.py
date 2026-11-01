"""Route package entrypoints."""

from flask import Flask


def register_service_routes(app: Flask) -> None:
    """Register the service-owned route groups.

    create_app calls this before loading flaskr/plugins, so plugin callbacks can
    find these view functions. The groups keep their own /api paths,
    independent of PATH_PREFIX.
    """
    from flaskr.service.billing.routes import register_billing_routes
    from flaskr.service.dashboard.routes import register_dashboard_routes
    from flaskr.service.learn.routes import register_learn_routes
    from flaskr.service.llm.route import register_llm_routes
    from flaskr.service.profile.routes import register_learner_profile_routes
    from flaskr.service.shifu.route import register_shifu_routes

    with app.app_context():
        register_billing_routes(app)
        register_dashboard_routes(app)
        register_learn_routes(app)
        register_llm_routes(app)
        register_learner_profile_routes(app)
        register_shifu_routes(app)


def register_route(app: Flask) -> Flask:
    """Register every API route group on the Flask application."""
    from flaskr.service.common.skill_request_analytics import (
        register_skill_request_analytics,
    )
    from flaskr.service.referral.routes import register_referral_routes

    from .callback import register_callback_handler
    from .common import register_common_handler
    from .config import register_config_handler
    from .creator_analytics import register_creator_analytics_handler
    from .dicts import register_dict_handler
    from .model_gateway import register_model_gateway_handler
    from .open_api import register_open_api_handler
    from .order import register_order_handler
    from .storage import register_storage_handler
    from .user import register_user_handler

    prefix = app.config.get("PATH_PREFIX", "")
    app = register_skill_request_analytics(app)
    app = register_common_handler(app)
    app = register_config_handler(app, prefix)
    app = register_storage_handler(app, prefix)
    app = register_user_handler(app, prefix + "/user")
    app = register_dict_handler(app, prefix + "/dict")
    app = register_order_handler(app, prefix + "/order")
    app = register_callback_handler(app, prefix + "/callback")
    app = register_open_api_handler(app, prefix + "/open-api/v1")
    app = register_model_gateway_handler(app, prefix + "/gateway")
    app = register_creator_analytics_handler(app, prefix + "/creator-analytics")
    register_referral_routes(app, prefix + "/referral")
    return app
