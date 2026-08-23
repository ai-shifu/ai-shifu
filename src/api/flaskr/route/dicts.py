"""Expose dicts HTTP routes."""

from flask import Flask

from flaskr.api.llm import get_current_models
from flaskr.service.common.dicts import get_all_dicts

from .common import bypass_token_validation, make_common_response


def register_dict_handler(app: Flask, path_prefix: str) -> Flask:
    """Register the dict routes on the Flask application."""

    @app.route(path_prefix + "/dicts", methods=["GET"])
    @bypass_token_validation
    def get_dicts() -> object:
        """Get all dictionaries.

        ---
        tags:
          - dict
        """
        return make_common_response(get_all_dicts(app))

    @app.route(path_prefix + "/models", methods=["GET"])
    @bypass_token_validation
    def get_models() -> object:
        """Get all models.

        ---
        tags:
          - dict
        """
        return make_common_response(get_current_models(app))

    return app
