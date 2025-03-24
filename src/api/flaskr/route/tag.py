from flask import Flask, request
from flaskr.service.common.models import raise_param_error
from .common import make_common_response
from ..service.tag.funs import (
    get_tag_type_list,
    get_tag_list,
    tag_add,
    tag_update,
    tag_drop,
)


def register_tag_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/tag-type-list", methods=["GET"])
    def run_tag_type_list():
        """
        获取标签类型列表
        ---
        tags:
            - 标签
        responses:
            200:
                description: 操作成功
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
                                    type: list
                                    description: 标签类型列表
        """
        return make_common_response(
            get_tag_type_list(
                app,
            )
        )

    @app.route(path_prefix + "/tag-list", methods=["GET"])
    def run_tag_list():
        """
        获取标签列表
        ---
        tags:
            - 标签
        responses:
            200:
                description: 操作成功
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
                                    type: list
                                    description: 标签列表
        """
        return make_common_response(
            get_tag_list(
                app,
            )
        )

    @app.route(path_prefix + "/tag-add", methods=["POST"])
    def run_tag_add():
        """
        创建标签
        ---
        tags:
        - 标签
        parameters:
            - name: tag_domain
              in: query
              description: 标签作用域
              required: true
              schema:
                type: string
            - name: tag_type
              in: query
              description: 标签类型
              required: true
              schema:
                type: string
            - name: tag_name
              in: query
              description: 标签名称
              required: true
              schema:
                type: string
        responses:
            200:
                description: 操作成功
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
                                    type: boolean
                                    description: 返回结果
        """
        tag_domain = request.get_json().get("tag_domain")
        if not tag_domain:
            raise_param_error("tag_domain is not found")
        if tag_domain not in ["rag"]:
            raise_param_error(f"tag_domain {tag_domain} is not supported")

        tag_type = request.get_json().get("tag_type")
        if not tag_type:
            raise_param_error("tag_type is not found")
        if tag_domain == "rag":
            if tag_type not in ["knowledge_base", "file"]:
                raise_param_error(
                    f"tag_type {tag_type} is not supported in tag_domain {tag_domain}"
                )

        tag_name = request.get_json().get("tag_name")
        if not tag_name:
            raise_param_error("tag_name is not found")

        user_id = request.user.user_id

        app.logger.info(f"tag_name: {tag_name}")
        app.logger.info(f"tag_type: {tag_type}")
        app.logger.info(f"user_id: {user_id}")

        return make_common_response(
            tag_add(
                app,
                tag_domain,
                tag_type,
                tag_name,
                user_id,
            )
        )

    @app.route(path_prefix + "/tag-update", methods=["POST"])
    def run_tag_update():
        """
        更新标签
        ---
        tags:
        - 标签
        parameters:
            - name: tag_id
              in: query
              description: 标签ID
              required: true
              schema:
                type: string
            - name: tag_name
              in: query
              description: 标签名称
              required: true
              schema:
                type: string
        responses:
            200:
                description: 操作成功
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
                                    type: boolean
                                    description: 返回结果
        """
        tag_id = request.get_json().get("tag_id")
        if not tag_id:
            raise_param_error("tag_id is not found")
        tag_name = request.get_json().get("tag_name")
        if not tag_name:
            raise_param_error("tag_name is not found")
        user_id = request.user.user_id
        app.logger.info(f"tag_id: {tag_id}")
        app.logger.info(f"tag_name: {tag_name}")
        app.logger.info(f"user_id: {user_id}")
        return make_common_response(
            tag_update(
                app,
                tag_id,
                tag_name,
                user_id,
            )
        )

    @app.route(path_prefix + "/tag-drop", methods=["POST"])
    def run_tag_drop():
        """
        删除标签
        ---
        tags:
        - 标签
        parameters:
            - name: tag_id_list
              in: query
              description: 标签ID列表
              required: true
              schema:
                type: list
        responses:
            200:
                description: 操作成功
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
                                    type: boolean
                                    description: 返回结果
        """
        tag_id_list = request.get_json().get("tag_id_list")
        if not tag_id_list:
            raise_param_error("tag_id_list is not found")
        app.logger.info(f"tag_id_list: {tag_id_list}")
        return make_common_response(
            tag_drop(
                app,
                tag_id_list,
            )
        )

    return app
