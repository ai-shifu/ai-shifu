from flask import Flask, Response, request
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.study import (
    get_lesson_tree_to_study,
    get_study_record,
    run_script,
    get_script_info,
    reset_user_study_info_by_lesson,
    set_script_content_operation,
)
from flaskr.service.study.const import VALID_INTERACTION_TYPES


def register_study_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/run", methods=["POST"])
    def run_lesson_script():
        """
        运行课程脚本
        ---
        tags:
        - 学习
        parameters:
            -   in: body
                name: body
                description: 运行课程脚本的请求体
                required: true
                schema:
                    type: object
                    properties:
                        course_id:
                            type: string
                            default: dfca19aab2654fe4882e002a58567240
                            description: 课程id
                        lesson_id:
                            type: string
                            description: 课时id
                        input:
                            type: string
                            description: 输入内容
                        input_type:
                            type: string
                            default: start
                            description: 输入类型（默认为 start）
                        script_id:
                            type: string
                            description: 脚本ID,如果为空则运行下一条，否则运行指定脚本
                        preview_mode:
                            type: boolean
                            default: false
                            description: 预览模式
        responses:
            200:
                description: 返回脚本运行结果

                content:
                    text/event-stream:
                        schema:
                             $ref: "#/components/schemas/ScriptDTO"
        """
        course_id = request.get_json().get("course_id", None)
        lesson_id = request.get_json().get("lesson_id", None)
        script_id = request.get_json().get("script_id", None)
        log_id = request.get_json().get("log_id", None)
        input = request.get_json().get("input", None)
        input_type = request.get_json().get("input_type", "start")
        preview_mode = request.get_json().get("preview_mode", False)
        if course_id == "":
            course_id = None
        user_id = request.user.user_id

        try:
            return Response(
                run_script(
                    app,
                    course_id=course_id,
                    lesson_id=lesson_id,
                    user_id=user_id,
                    input=input,
                    input_type=input_type,
                    script_id=script_id,
                    log_id=log_id,
                    preview_mode=preview_mode,
                ),
                headers={"Cache-Control": "no-cache"},
                mimetype="text/event-stream",
            )
        except Exception as e:
            app.logger.error(e)
            # return make_common_response("系统错误")

    # ensure the instance folder exists

    @app.route(path_prefix + "/get_lesson_tree", methods=["GET"])
    def get_lesson_tree_study():
        """
        获取课程树
        ---
        tags:
        - 学习
        parameters:
        -   name: course_id
            in: query
            type: string
            required: true
            description: 课程ID
        responses:
            200:
                description: 返回课程树
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
                                    $ref: "#/components/schemas/AICourseDTO"
            400:
                description: 参数错误
        """
        course_id = request.args.get("course_id")
        if not course_id:
            course_id = None
        user_id = request.user.user_id
        return make_common_response(get_lesson_tree_to_study(app, user_id, course_id))

    @app.route(path_prefix + "/get_lesson_study_record", methods=["GET"])
    def get_lesson_study_record():
        """
        获取课程学习记录
        ---
        tags:
        - 学习
        parameters:
        -   name: lesson_id
            in: query
            type: string
            required: true
            description: 课时ID
        responses:
            200:
                description: 返回课程学习记录
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
                                    $ref: "#/components/schemas/StudyRecordDTO"
            400:
                description: 参数错误
        """
        lesson_id = request.args.get("lesson_id")
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        user_id = request.user.user_id
        return make_common_response(get_study_record(app, user_id, lesson_id))

    @app.route(path_prefix + "/get-lesson-study-progress", methods=["GET"])
    def get_lesson_study_progress():
        """
        获取课程学习进度
        ---
        tags:
        - 学习
        parameters:
        -   name: lesson_id
            in: query
            type: string
            required: true
            description: 课时ID
        responses:
            200:
                description: 返回课程学习进度
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
                                    $ref: "#/components/schemas/StudyRecordProgressDTO"
            400:
                description: 参数错误
        """
        lesson_id = request.args.get("lesson_id")
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        user_id = request.user.user_id
        return make_common_response(get_lesson_study_progress(app, user_id, lesson_id))

    @app.route(path_prefix + "/query-script-into", methods=["GET"])
    def query_script_info():
        """
        查询脚本信息

        ---
        tags:

        - 学习
        parameters:
            -   name: script_id
                in: query
                type: string
                required: true
                description: 脚本ID
        responses:
            200:
                description: 返回脚本信息
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
                                    $ref: "#/components/schemas/ScriptInfoDTO"
            400:
                description: 参数错误
        """
        script_id = request.args.get("script_id")
        if not script_id:
            raise_param_error("script_id is not found")
        user_id = request.user.user_id
        return make_common_response(get_script_info(app, user_id, script_id))

    @app.route(path_prefix + "/reset-study-progress", methods=["POST"])
    def reset_study_progress():
        """
        重置学习进度
        ---
        tags:
        - 学习
        parameters:
            -   in: body
                name: body
                description: 重置学习进度的请求体
                required: true
                schema:
                    type: object
                    properties:
                        lesson_id:
                            type: string
                            description: 课时id
        responses:
            200:
                description: 返回重置结果
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
            400:
                description: 参数错误
        """
        lesson_id = request.get_json().get("lesson_id")
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        user_id = request.user.user_id
        return make_common_response(
            reset_user_study_info_by_lesson(app, user_id, lesson_id)
        )

    @app.route(path_prefix + "/script-content-operation", methods=["POST"])
    def script_content_operation():
        """
        对脚本内容进行操作(点赞点踩)
        ---
        tags:
        - 学习
        parameters:
            -   in: body
                name: body
                description: 对脚本内容进行操作(点赞点踩)
                required: true
                schema:
                    type: object
                    properties:
                        script_id:
                            type: string
                            description: script_id
        parameters:
            -   in: body
                name: body
                description: 对脚本内容进行操作(点赞点踩)
                required: true
                schema:
                    type: object
                    properties:
                        properties:
                            log_id:
                                type: string
                                description: log_id
                            interaction_type:
                                type: integer
                                description: 0-default, 1-like, 2-dislike
        responses:
            200:
                description: 返回处理结果
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
            400:
                description: 参数错误
        """
        log_id = request.get_json().get("log_id")
        interaction_type = request.get_json().get("interaction_type", None)

        if interaction_type not in VALID_INTERACTION_TYPES:
            raise_param_error("interaction_type wrong value range")
        if not log_id:
            raise_param_error("log_id is not found")
        user_id = request.user.user_id
        return make_common_response(
            set_script_content_operation(app, user_id, log_id, interaction_type)
        )

    return app
