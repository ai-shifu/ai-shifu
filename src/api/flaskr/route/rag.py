from flask import Flask, request
from flaskr.service.common.models import raise_param_error

from .common import bypass_token_validation, make_common_response
from ..service.rag.funs import (
    get_kb_list,
    kb_create,
    kb_drop,
    oss_file_upload,
    kb_file_upload,
    retrieval,
)


def register_rag_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/kb_list", methods=["GET"])
    @bypass_token_validation
    def run_kb_list():
        """
        获取知识库列表
        ---
        tags:
        - 知识库
        responses:
            200:
                description: 获取知识库列表成功
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
                                    description: 知识库ID列表
        """
        return make_common_response(
            get_kb_list(
                app,
            )
        )

    @app.route(path_prefix + "/kb_create", methods=["POST"])
    @bypass_token_validation
    def run_kb_create():
        """
        创建知识库
        ---
        tags:
        - 知识库
        parameters:
            - name: kb_id
              in: query
              description: 知识库ID
              required: true
              schema:
                type: string
            - name: embedding_model
              in: query
              description: Embedding模型名称
              required: false
              schema:
                type: string
            - name: dim
              in: query
              description: 向量维度
              required: false
              schema:
                type: int
            - name: kb_category_0
              in: query
              description: 知识库顶级分类
              required: false
              schema:
                type: string
            - name: kb_category_1
              in: query
              description: 知识库一级分类
              required: false
              schema:
                type: string
            - name: kb_category_2
              in: query
              description: 知识库二级分类
              required: false
              schema:
                type: string
        responses:
            200:
                description: 创建知识库成功
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
                                    type: string
                                    description: 测试返回结果
        """
        kb_id = request.get_json().get("kb_id")
        if not kb_id:
            raise_param_error("kb_id is not found")
        embedding_model = request.get_json().get("embedding_model", None)
        dim = request.get_json().get("dim", None)
        if embedding_model is None and dim is None:
            embedding_model = app.config["DEFAULT_EMBEDDING_MODEL"]
            dim = app.config["DEFAULT_EMBEDDING_MODEL_DIM"]
        elif embedding_model is None or dim is None:
            raise_param_error("embedding_model and dim is not found")
        if isinstance(dim, str):
            dim = int(dim)
        if not isinstance(dim, int):
            raise_param_error("dim data type is not found")
        kb_category_0 = request.get_json().get("kb_category_0", "")
        kb_category_1 = request.get_json().get("kb_category_1", "")
        kb_category_2 = request.get_json().get("kb_category_2", "")
        app.logger.info(f"kb_id: {kb_id}")
        app.logger.info(f"embedding_model: {embedding_model}")
        app.logger.info(f"dim: {dim}")
        app.logger.info(f"kb_category_0: {kb_category_0}")
        app.logger.info(f"kb_category_1: {kb_category_1}")
        app.logger.info(f"kb_category_2: {kb_category_2}")
        return make_common_response(
            kb_create(
                app,
                kb_id,
                embedding_model,
                dim,
                kb_category_0,
                kb_category_1,
                kb_category_2,
            )
        )

    @app.route(path_prefix + "/kb_drop", methods=["POST"])
    @bypass_token_validation
    def run_kb_drop():
        """
        删除知识库
        ---
        tags:
        - 知识库
        parameters:
            - name: kb_id_list
              in: query
              description: 知识库ID列表
              required: true
              schema:
                type: list
        responses:
            200:
                description: 删除知识库成功
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
                                    type: string
                                    description: success
        """
        kb_id_list = request.get_json().get("kb_id_list")
        if not kb_id_list:
            raise_param_error("kb_id_list is not found")
        app.logger.info(f"kb_id_list: {kb_id_list}")
        return make_common_response(
            kb_drop(
                app,
                kb_id_list,
            )
        )

    @app.route(path_prefix + "/oss_file_upload", methods=["POST"])
    @bypass_token_validation
    def run_oss_file_upload():
        """
        OSS文件上传
        ---
        tags:
            - 知识库
        parameters:
            - in: formData
              name: upload_file
              type: file
              required: true
              description: 文件
        responses:
            200:
                description: 上传成功
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
                                    type: string
                                    description: OSS文件KEY
        """
        app.logger.info("enter file_upload!")
        upload_file = request.files.get("upload_file", None)
        if not upload_file:
            raise_param_error("upload_file")
        return make_common_response(oss_file_upload(app, upload_file))

    @app.route(path_prefix + "/kb_file_upload", methods=["POST"])
    @bypass_token_validation
    def run_kb_file_upload():
        """
        知识库文件上传
        ---
        tags:
        - 知识库
        parameters:
            - name: kb_id
              in: query
              description: 知识库ID
              required: true
              schema:
                type: string
            - name: file_key
              in: query
              description: OSS文件KEY
              required: true
              schema:
                type: string
            - name: split_separator
              in: query
              description: 分段标识符
              required: false
              schema:
                type: string
            - name: embedding_model
              in: query
              description: Embedding模型
              required: false
              schema:
                type: string
        responses:
            200:
                description: 文件处理完成
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
                                    description: success
        """
        kb_id = request.get_json().get("kb_id", None)
        if not kb_id:
            raise_param_error("kb_id is not found")
        file_key = request.get_json().get("file_key", None)
        if not file_key:
            raise_param_error("file_key is not found")
        split_separator = request.get_json().get("split_separator", "\n\n")
        split_max_length = request.get_json().get("split_max_length", 500)
        split_chunk_overlap = request.get_json().get("split_chunk_overlap", 50)
        embedding_model = request.get_json().get("embedding_model", None)
        app.logger.info(f"file_key: {file_key}")
        app.logger.info(f"split_separator: {split_separator}")
        app.logger.info(f"embedding_model: {embedding_model}")
        return make_common_response(
            kb_file_upload(
                app,
                kb_id,
                file_key,
                split_separator,
                split_max_length,
                split_chunk_overlap,
                embedding_model,
            )
        )

    @app.route(path_prefix + "/retrieval", methods=["POST"])
    @bypass_token_validation
    def run_retrieval():
        """
        知识检索
        ---
        tags:
        - 知识库
        parameters:
            - name: kb_id
              in: query
              description: 知识库ID
              required: true
              schema:
                type: string
            - name: query
              in: query
              description: 查询文本
              required: true
              schema:
                type: int
            - name: embedding_model
              in: query
              description: Embedding模型
              required: false
              schema:
                type: string
        responses:
            200:
                description: 检索成功
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
                                    type: string
                                    description: 检索结果
        """
        kb_id = request.get_json().get("kb_id")
        if not kb_id:
            raise_param_error("kb_id is not found")
        query = request.get_json().get("query")
        if not query:
            raise_param_error("query is not found")
        embedding_model = request.get_json().get("embedding_model", None)
        app.logger.info(f"kb_id: {kb_id}")
        app.logger.info(f"query: {query}")
        return make_common_response(
            retrieval(
                app,
                kb_id,
                query,
                embedding_model,
            )
        )

    return app
