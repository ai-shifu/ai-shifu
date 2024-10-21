from flask import Flask, request

from ...service.user.admin import get_user_list
from ..common import make_common_response


def register_user_route(app: Flask, path_prefix):

    @app.route(path_prefix + "/user-list", methods=["POST"])
    def get_c_user_list():
        """
        获取用户列表
        ---
        tags:
            - 用户
        responses:
            200:
                description: 返回用户列表
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    type: object
                                    description: 用户列表
        """
        page_size = request.get_json().get("page_size", 20)
        page_index = request.get_json().get("page_index", 1)
        query = request.get_json().get("query", {})

        return make_common_response(get_user_list(app, page_index, page_size, query))

    return app
