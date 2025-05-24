from flask import Flask, request
from flaskr.service.common.models import raise_param_error
from flaskr.service.lesson.funs import (
    get_course_info,
    update_course_info,
    get_course_list,
)
from .common import bypass_token_validation, make_common_response


def register_course_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/update_course_info", methods=["POST"])
    @bypass_token_validation
    def update_course_info_api():
        """

        update course info
        ---
        tags:
        - 课程
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        course_id:
                            type: string
                            description: 课程id
                            required: true
                        course_name:
                            type: string
                            description: 课程名称
                            required: true
                        course_desc:
                            type: string
                            description: 课程描述
                            required: false
                        course_price:
                            type: number
                            description: 课程价格
                            required: false
                        course_status:
                            type: integer
                            description: 课程状态
                            required: false
                        course_feishu_id:
                            type: string
                            description: 课程飞书id
                            required: false
                        course_teacher_avatar:
                            type: string
                            description: 课程老师头像
                            required: false
        responses:
            200:
                description: 更新课程信息成功
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码


        """

        course_id = request.json.get("course_id")
        course_name = request.json.get("course_name")
        course_desc = request.json.get("course_desc")
        course_price = request.json.get("course_price")
        course_status = request.json.get("course_status")
        course_feishu_id = request.json.get("course_feishu_id")
        course_teacher_avatar = request.json.get("course_teacher_avatar")
        if course_id is None or course_name is None:
            raise_param_error("course_id and course_name is required")
        if course_name is None or len(course_name) == 0:
            raise_param_error("course_name is required")

        if course_desc is None:
            course_desc = ""
        if course_price is None:
            course_price = 0
        if course_status is None:
            course_status = 0
        if course_feishu_id is None:
            course_feishu_id = ""
        if course_teacher_avatar is None:
            course_teacher_avatar = ""
        return make_common_response(
            update_course_info(
                app,
                course_id,
                course_name,
                course_desc,
                course_price,
                course_status,
                course_feishu_id,
                course_teacher_avatar,
            )
        )

    @app.route(path_prefix + "/get_course_list", methods=["GET"])
    @bypass_token_validation
    def get_course_list_api():
        """

        get course list api
        ---
        tags:
        - course

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
                                    description: 课程列表
                                    items:
                                        $ref: '#/components/schemas/AICourseDTO'
        """
        return make_common_response(get_course_list(app))

    @app.route(path_prefix + "/get-course-info", methods=["GET"])
    @bypass_token_validation
    def get_course_info_api():
        """

        get course info api
        ---
        tags:
        - course
        parameters:
            -   in: query
                required: true
                schema:
                    properties:
                        course_id:
                            type: string
                            description: 课程id
        responses:
            200:
                description: 获取课程信息成功
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
                                    $ref: '#/components/schemas/AICourseDTO'
        """
        course_id = request.args.get("course_id", None)
        preview_mode = request.args.get("preview_mode", "False").lower() == "true"
        return make_common_response(get_course_info(app, course_id, preview_mode))

    return app
