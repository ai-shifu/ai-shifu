from flask import Flask

from flaskr.api.llm import get_current_models

from ..service.common.dicts import get_all_dicts
from .common import bypass_token_validation, make_common_response


def register_dict_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/dicts", methods=["GET"])
    @bypass_token_validation
    def get_dicts():
        """获取所有字典.
        ---
        tags:
          - 字典
        """
        return make_common_response(get_all_dicts(app))

    @app.route(path_prefix + "/models", methods=["GET"])
    @bypass_token_validation
    def get_models():
        """获取所有模型.
        ---
        tags:
          - 字典
        """
        return make_common_response(get_current_models(app))

    return app
