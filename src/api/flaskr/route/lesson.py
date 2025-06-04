from flask import Flask, request
from flaskr.service.lesson.funs import delete_lesson, update_lesson_ask_info
from flaskr.service.common.models import raise_param_error
from flaskr.service.lesson.const import LESSON_TYPE_NORMAL
from .common import bypass_token_validation, make_common_response
from ..service.lesson import update_lesson_info, get_lessons


def register_lesson_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/update_lesson", methods=["GET"])
    @bypass_token_validation
    def update_lesson():
        """
        从飞书文档中更新课程
        ---
        tags:
        - 课程
        parameters:
            - name: doc_id
              in: query
              description: 文档id
              required: true
              schema:
                type: string
            - name: table_id
              in: query
              description: 课程表格id
              required: true
              schema:
                type: string
            - name: title
              in: query
              description: 课程标题
              required: true
              schema:
                type: string
            - name: index
              in: query
              description: 课程序号
              required: true
              schema:
                type: string
            - name: view_id
              in: query
              description: 视图id
              required: true
              schema:
                type: string
            - name: lesson_type
              in: query
              description: 课程类型
              required: false
              schema:
                type: string
            - name: app_id
              in: query
              description: 飞书应用id,不传则使用默认的飞书应用
              required: false
              schema:
                type: string
            - name: app_secret
              in: query
              description: 飞书应用秘钥,不传则使用默认的飞书应用秘钥
              required: false
              schema:
                type: string
            - name: course_id
              in: query
              description: 课程id
              required: false
              schema:
                type: string
        """
        doc_id = request.args.get("doc_id")
        table_id = request.args.get("table_id")
        title = request.args.get("title")
        index = request.args.get("index")
        view_id = request.args.get("view_id")
        lesson_type = request.args.get("lesson_type", LESSON_TYPE_NORMAL)
        app_id = request.args.get("app_id", None)
        app_secret = request.args.get("app_secret", None)
        course_id = request.args.get("course_id", None)
        if not doc_id:
            raise_param_error("doc_id is not found")
        if not table_id:
            raise_param_error("table_id is not found")
        if not title:
            raise_param_error("title is not found")
        if not index:
            raise_param_error("index is not found")
        return make_common_response(
            update_lesson_info(
                app,
                doc_id,
                table_id,
                view_id,
                title,
                index,
                lesson_type,
                app_id,
                app_secret,
                course_id,
            )
        )

    @app.route(path_prefix + "/get_chatper_info", methods=["GET"])
    @bypass_token_validation
    def get_chatper_info():
        """
        获取课程列表
        ---
        tags:
        - 课程
        parameters:
            - name: doc_id
              in: query
              description: 文档id
              required: true
        responses:
            200:
                description: 获取课程列表成功
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
                                    type: array
                                    items:
                                        $ref: "#/components/schemas/AICourseDetailDTO"
        """
        doc_id = request.args.get("doc_id")
        if not doc_id:
            raise_param_error("doc_id is not found")
        return make_common_response(get_lessons(app, doc_id))

    @app.route(path_prefix + "/delete_lesson", methods=["GET"])
    @bypass_token_validation
    def delete_lesson_by_table():
        """
        删除课程
        ---
        tags:
        - 课程
        parameters:
            - name: table_id
              in: query
              description: 课程表格id 或是转入表格Id ，或是传入课程ID和课程编号
              required: true
              schema:
                type: string
            - name: course_id
              in: query
              description: 课程id
              required: true
              schema:
                type: string
            - name: lesson_no
              in: query
              description: 课程编号
              required: true
              schema:
                type: string
        """
        lesson_id = request.args.get("table_id", None)
        course_id = request.args.get("course_id", None)
        lesson_no = request.args.get("lesson_no", None)

        if not lesson_id and not course_id and not lesson_no:
            raise_param_error("lesson_id or course_id or lesson_no is not found")
        return make_common_response(delete_lesson(app, lesson_id, course_id, lesson_no))

    @app.route(path_prefix + "/get_lesson_detail", methods=["GET"])
    @bypass_token_validation
    def get_lesson_detail():
        """
        获取课程详情
        ---
        tags:
        - 课程
        parameters:
            - name: lesson_id
              in: query
              description: 课程id
              required: true
              schema:
                type: string
        responses:
            200:
                description: 获取课程详情成功
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
                                    $ref: "#/components/schemas/AILessonDetailDTO"

        """
        lesson_id = request.args.get("lesson_id")
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        return make_common_response(get_lesson_detail(app, lesson_id))

    @app.route(path_prefix + "/update_ask_info", methods=["POST"])
    @bypass_token_validation
    def update_ask_info():
        """
        更新课程问答信息
        ---
        tags:
        - 课程
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        lesson_id:
                            type: string
                            description: 课程id
                        lesson_ask_count_limit:
                            type: integer
                            description: 课程追问次数限制
                            required: true
                        lesson_ask_model:
                            type: string
                            description: 课程追问模型
                            required: true
                        lesson_ask_prompt:
                            type: string
                            description: 课程追问提示词
                            required: true
                        lesson_ask_count_history:
                            type: integer
                            description: 课程追问包含的历史记录数
                            required: true
                        lesson_summary:
                            type: string
                            description: 课程总结，用于追问场景
                            required: true
                        lesson_language:
                            type: string
                            description: 课程语言,默认是zh,暂时不启用
                            required: false
                        lesson_name_multi_language:
                            type: string
                            description: 课程名称多语言,默认是zh,暂时不启用
                            required: false
                        lesson_summary_multi_language:
                            type: string
                            description: 课程总结多语言,默认是zh,暂时不启用
                            required: false
        responses:
            200:
                description: 更新课程问答信息成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    type: boolean
                                    description: 更新结果
        """
        lesson_id = request.get_json().get("lesson_id")
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        lesson_ask_count_limit = request.get_json().get("lesson_ask_count_limit")
        if not lesson_ask_count_limit:
            raise_param_error("lesson_ask_count_limit is not found")
        lesson_ask_model = request.get_json().get("lesson_ask_model")
        if not lesson_ask_model:
            raise_param_error("lesson_ask_model is not found")
        lesson_ask_prompt = request.get_json().get("lesson_ask_prompt")
        if not lesson_ask_prompt:
            raise_param_error("lesson_ask_prompt is not found")
        lesson_ask_count_history = request.get_json().get("lesson_ask_count_history")
        if not lesson_ask_count_history:
            raise_param_error("lesson_ask_count_history is not found")
        lesson_summary = request.get_json().get("lesson_summary")
        if not lesson_summary:
            raise_param_error("lesson_summary is not found")
        lesson_language = request.get_json().get("lesson_language", "zh")
        if not lesson_language:
            raise_param_error("lesson_language is not found")
        lesson_name_multi_language = request.get_json().get(
            "lesson_name_multi_language", "{}"
        )
        if not lesson_name_multi_language:
            raise_param_error("lesson_name_multi_language is not found")
        lesson_summary_multi_language = request.get_json().get(
            "lesson_summary_multi_language", "{}"
        )

        app.logger.info(
            "update_lesson_ask_info: lesson_id: %s, lesson_ask_count_limit: %s, lesson_ask_model: %s, lesson_ask_prompt: %s, lesson_ask_count_history: %s, lesson_summary: %s, lesson_language: %s, lesson_name_multi_language: %s, lesson_summary_multi_language: %s",  # noqa
            lesson_id,
            lesson_ask_count_limit,
            lesson_ask_model,
            lesson_ask_prompt,
            lesson_ask_count_history,
            lesson_summary,
            lesson_language,
            lesson_name_multi_language,
            lesson_summary_multi_language,
        )
        return make_common_response(
            update_lesson_ask_info(
                app,
                lesson_id,
                lesson_ask_count_limit,
                lesson_ask_model,
                lesson_ask_prompt,
                lesson_ask_count_history,
                lesson_summary,
                lesson_language,
                lesson_name_multi_language,
                lesson_summary_multi_language,
            )
        )

    return app
