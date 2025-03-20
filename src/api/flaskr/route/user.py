from flask import Flask, request, make_response

from flaskr.service.common.models import raise_param_error
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from ..service.user import (
    create_new_user,
    verify_user,
    validate_user,
    update_user_info,
    change_user_passwd,
    require_reset_pwd_code,
    reset_pwd,
    generate_temp_user,
    generation_img_chk,
    send_sms_code,
    verify_sms_code,
    upload_user_avatar,
    update_user_open_id,
)
from ..service.feedback.funs import submit_feedback
from .common import make_common_response, bypass_token_validation, by_pass_login_func
from flaskr.dao import db
from flaskr.i18n import set_language


def register_user_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/register", methods=["POST"])
    @bypass_token_validation
    def register():
        """
        注册用户
        ---
        tags:
          - user
        parameters:
            -   in:   body
                required: true
                schema:
                    properties:
                        username:
                            type: string
                            description: 用户名
                        password:
                            type: string
                            description: 密码
                        email:
                            type: string
                            description: 邮箱
                        name:
                            type: string
                            description: 姓名
                        mobile:
                            type: string
                            description: 手机号
        responses:
            200:
                description: 注册成功
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
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: 参数错误
        """
        app.logger.info("register")
        username = request.get_json().get("username", "")
        password = request.get_json().get("password", "")
        email = request.get_json().get("email", "")
        name = request.get_json().get("name", "")
        mobile = request.get_json().get("mobile", "")
        user_token = create_new_user(app, username, name, password, email, mobile)
        resp = make_response(make_common_response(user_token))
        return resp

    @app.route(path_prefix + "/login", methods=["POST"])
    @bypass_token_validation
    def login():
        """
        用户登录
        ---
        tags:
            - user
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        username:
                            type: string
                            description: 用户名
                        password:
                            type: string
                            description: 密码
            -   in: header
                required: false
                name: X-API-MODE
                schema:
                    type: string
                    description: 模式 (api, admin)
                    default: api
        responses:
            200:
                description: 登录成功
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
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: 参数错误
        """
        app.logger.info("login")
        username = request.get_json().get("username", "")
        password = request.get_json().get("password", "")
        user_token = verify_user(app, username, password)
        resp = make_response(make_common_response(user_token))
        return resp

    @app.before_request
    def before_request():
        if (
            request.endpoint
            in [
                "login",
                "register",
                "require_reset_code",
                "reset_password",
                "invoke",
                "update_lesson",
            ]
            or request.endpoint in by_pass_login_func
            or request.endpoint is None
        ):
            return

        token = request.cookies.get("token", None)
        if not token:
            token = request.args.get("token", None)
        if not token:
            token = request.headers.get("Token", None)
        if not token and request.method.upper() == "POST" and request.is_json:
            token = request.get_json().get("token", None)
        token = str(token)
        if not token and request.endpoint in by_pass_login_func:
            return
        user = validate_user(app, token)
        set_language(user.language)
        request.user = user

    @app.route(path_prefix + "/info", methods=["GET"])
    def info():
        """
        获取用户信息
        ---
        tags:
            - user
        responses:
            200:
                description: 获取用户信息
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
                                    $ref: "#/components/schemas/UserInfo"
        """
        return make_common_response(request.user)

    @app.route(path_prefix + "/update_info", methods=["POST"])
    def update_info():
        email = request.get_json().get("email", None)
        name = request.get_json().get("name", "")
        mobile = request.get_json().get("mobile", None)
        return make_common_response(
            update_user_info(app, request.user, name, email, mobile)
        )

    @app.route(path_prefix + "/update_password", methods=["POST"])
    def update_password():
        old_password = request.get_json().get("old_password", None)
        new_password = request.get_json().get("new_password", None)
        return make_common_response(
            change_user_passwd(app, request.user, old_password, new_password)
        )

    @app.route(path_prefix + "/require_reset_code", methods=["POST"])
    def require_reset_code():
        username = request.get_json().get("username", None)
        return make_common_response(require_reset_pwd_code(app, username))

    @app.route(path_prefix + "/reset_password", methods=["POST"])
    def reset_password():
        username = request.get_json().get("username", None)
        code = request.get_json().get("code", None)
        new_password = request.get_json().get("new_password", None)
        return make_common_response(reset_pwd(app, username, code, new_password))

    @app.route(path_prefix + "/require_tmp", methods=["POST"])
    @bypass_token_validation
    def require_tmp():
        """
        临时登录用户
        ---
        tags:
            - user
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        temp_id:
                            type: string
                            description: 临时用户ID
                        source:
                            type: string
                            description: 来源
                        wxcode:
                            type: string
                            description: 微信code
                        language:
                            type: string
                            description: 语言
        responses:
            200:
                description: 临时用户登录成功
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
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: 参数错误


        """
        tmp_id = request.get_json().get("temp_id", None)
        source = request.get_json().get("source", "web")
        wx_code = request.get_json().get("wxcode", None)
        language = request.get_json().get("language", "en-US")
        app.logger.info(
            f"require_tmp tmp_id: {tmp_id}, source: {source}, wx_code: {wx_code}"
        )
        if not tmp_id:
            raise_param_error("temp_id")
        user_token = generate_temp_user(app, tmp_id, source, wx_code, language)
        resp = make_response(make_common_response(user_token))
        return resp

    @app.route(path_prefix + "/generate_chk_code", methods=["POST"])
    # @bypass_token_validation
    def generate_chk_code():
        """
        生成图形验证码
        ---
        tags:
            - user
        """
        mobile = request.get_json().get("mobile", None)
        if not mobile:
            raise_param_error("mobile")
        return make_common_response(generation_img_chk(app, mobile))

    @app.route(path_prefix + "/send_sms_code", methods=["POST"])
    # @bypass_token_validation
    def send_sms_code_api():
        """
        发送短信验证码
        ---
        tags:
           - user

        parameters:
          - in: body
            required: true
            schema:
              properties:
                mobile:
                  type: string
                  description: 手机号
                check_code:
                  type: string
                  description: 图形验证码
              required:
                - mobile
                - check_code
        responses:
            200:
                description: 发送成功
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
                                    description: 短信验证码
                                    schema:
                                        properties:
                                            expire_in:
                                                type: integer
                                                description: 短信验证码


            400:
                description: 参数错误

        """
        mobile = request.get_json().get("mobile", None)
        check_code = request.get_json().get("check_code", None)
        if not mobile:
            raise_param_error("mobile")
        if not check_code:
            raise_param_error("check_code")
        return make_common_response(send_sms_code(app, mobile, check_code))

    @app.route(path_prefix + "/verify_sms_code", methods=["POST"])
    # @bypass_token_validation
    def verify_sms_code_api():
        with app.app_context():

            mobile = request.get_json().get("mobile", None)
            sms_code = request.get_json().get("sms_code", None)
            user_id = (
                None if getattr(request, "user", None) is None else request.user.user_id
            )
            if not mobile:
                raise_param_error("mobile")
            if not sms_code:
                raise_param_error("sms_code")
            ret = verify_sms_code(app, user_id, mobile, sms_code)
            db.session.commit()
            resp = make_response(make_common_response(ret))
            return resp

    @app.route(path_prefix + "/get_profile", methods=["GET"])
    def get_profile():
        """
        获取用户信息
        ---
        tags:
            - user
        responses:
            200:
                description: 返回用户信息
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
                                    description: 用户信息

        """
        return make_common_response(get_user_profile_labels(app, request.user.user_id))

    @app.route(path_prefix + "/update_profile", methods=["POST"])
    def update_profile():
        """
        更新用户信息
        ---
        tags:
            - user
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    profiles:
                        type: array
                        items:
                            properties:
                                key:
                                    type: string
                                    description: 属性名
                                value:
                                    type: string
                                    description: 属性值
        responses:
            200:
                description: 更新成功
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
        """
        profiles = request.get_json().get("profiles", None)
        if not profiles:
            raise_param_error("profiles")
        with app.app_context():
            ret = update_user_profile_with_lable(
                app, request.user.user_id, profiles, update_all=True
            )
            db.session.commit()
            return make_common_response(ret)

    @app.route(path_prefix + "/upload_avatar", methods=["POST"])
    def upload_avatar():
        """
        上传头像
        ---
        tags:
            - user
        parameters:
            - in: formData
              name: avatar
              type: file
              required: true
              description: 头像文件
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
                                    description: 头像地址
        """
        avatar = request.files.get("avatar", None)
        if not avatar:
            raise_param_error("avatar")
        return make_common_response(
            upload_user_avatar(app, request.user.user_id, avatar)
        )

    @app.route(path_prefix + "/update_openid", methods=["POST"])
    def update_wechat_openid():
        """
        Update Wechat OpenID
        ---
        summary: 更新微信openid
        tags:
            - user
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    wxcode:
                        type: string
                        description: 微信code
        responses:
            200:
                description: 更新成功
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
                                    description: openid
        """
        code = request.get_json().get("wxcode", None)
        app.logger.info(f"update_wechat_openid code: {code}")
        if not code:
            raise_param_error("wxcode")
        return make_common_response(
            update_user_open_id(app, request.user.user_id, code)
        )

    @app.route(path_prefix + "/submit-feedback", methods=["POST"])
    def sumbit_feedback_api():
        """
        提交反馈
        ---
        tags:
            - user
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    feedback:
                        type: string
                        description: 反馈内容
        responses:
            200:
                description: 提交成功
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
                                    type: integer
                                    description: 反馈ID
            400:
                description: 参数错误
        """

        user_id = request.user.user_id
        feedback = request.get_json().get("feedback", None)
        if not feedback:
            raise_param_error("feedback")
        return make_common_response(submit_feedback(app, user_id, feedback))

    # 健康检查
    @app.route("/health", methods=["GET"])
    @bypass_token_validation
    def health():
        app.logger.info("health")
        return make_common_response("ok")

    return app
