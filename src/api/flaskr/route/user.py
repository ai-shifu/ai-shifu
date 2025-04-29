from flask import Flask, request, make_response, current_app
from functools import wraps
import threading

from flaskr.service.common.models import raise_param_error
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from ..service.user import (
    create_new_admin_user,
    verify_user,
    validate_user,
    update_user_info,
    change_user_passwd,
    require_reset_pwd_code,
    reset_pwd,
    generate_temp_user,
    generation_img_chk,
    send_sms_code,
    send_email_code,
    verify_sms_code,
    verify_mail_code,
    set_user_password,
    upload_user_avatar,
    update_user_open_id,
)
from ..service.feedback.funs import submit_feedback
from .common import make_common_response, bypass_token_validation, by_pass_login_func
from flaskr.dao import db
from flaskr.i18n import set_language

thread_local = threading.local()


def optional_token_validation(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get("token", None)
        if not token:
            token = request.args.get("token", None)
        if not token:
            token = request.headers.get("Token", None)
        if not token and request.method.upper() == "POST" and request.is_json:
            token = request.get_json().get("token", None)

        if token:
            token = str(token)
            user = validate_user(current_app, token)
            set_language(user.language)
            request.user = user
        return f(*args, **kwargs)

    return decorated_function


def register_user_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/register", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def register():
        """
        register
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
                            description: user name
                        password:
                            type: string
                            description: password
                        email:
                            type: string
                            description: email
                        name:
                            type: string
                            description: name
                        mobile:
                            type: string
                            description: mobile phone number
        responses:
            200:
                description: Registration success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: parameter error
        """
        app.logger.info("register")
        username = request.get_json().get("username", "")
        password = request.get_json().get("password", "")
        email = request.get_json().get("email", "")
        name = request.get_json().get("name", "")
        mobile = request.get_json().get("mobile", "")
        user_token = create_new_admin_user(app, username, name, password, email, mobile)
        resp = make_response(make_common_response(user_token))
        return resp

    @app.route(path_prefix + "/login", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def login():
        """
        user login
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
                            description: user name
                        password:
                            type: string
                            description: password
            -   in: header
                required: false
                name: X-API-MODE
                schema:
                    type: string
                    description: mode (api, admin)
                    default: api
        responses:
            200:
                description: login is success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: parameter error
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
        get user information
        ---
        tags:
            - user
        responses:
            200:
                description: get user information
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
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
        Temp login user
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
                            description: Temp login user ID
                        source:
                            type: string
                            description: source
                        wxcode:
                            type: string
                            description: WeChat code
                        language:
                            type: string
                            description: language
        responses:
            200:
                description: Temp user login success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: parameter error


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
        Generating a Graphical Captcha
        ---
        tags:
            - user
        parameters:
          - in: body
            required: true
            description: mobile or email
            schema:
              properties:
                mobile:
                  type: string
                  description: mobile
                mail:
                  type: string
                  description: email
              required:
                - mobile
                - mail
        responses:
            200:
                description:
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return message
                                data:
                                    type: object
                                    description: return message
                                    properties:
                                        expire_in:
                                            type: string
                                            description: expire in
                                        img:
                                            type: string
                                            description: img png base64


            400:
                description: parameter error
        """
        mobile = request.get_json().get("mobile", None)
        mail = request.get_json().get("mail", None)
        identifying_account = ""
        if mobile:
            identifying_account = mobile
        if mail:
            identifying_account = mail
        if not identifying_account:
            raise_param_error("mobile or mail is required")
        return make_common_response(generation_img_chk(app, identifying_account))

    @app.route(path_prefix + "/send_sms_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def send_sms_code_api():
        """
        Send SMS Captcha
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
                  description: mobile phone number
              required:
                - mobile
        responses:
            200:
                description: sent success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    description: SMS Captcha
                                    schema:
                                        properties:
                                            expire_in:
                                                type: integer
                                                description: SMS Captcha


            400:
                description: parameter error

        """
        mobile = request.get_json().get("mobile", None)
        if not mobile:
            raise_param_error("mobile")
        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr
        return make_common_response(send_sms_code(app, mobile, client_ip))

    @app.route(path_prefix + "/verify_sms_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def verify_sms_code_api():
        """
        Send verify email code
        ---
        tags:
           - user
        """
        with app.app_context():

            mobile = request.get_json().get("mobile", None)
            sms_code = request.get_json().get("sms_code", None)
            course_id = request.get_json().get("course_id", None)
            user_id = (
                None if getattr(request, "user", None) is None else request.user.user_id
            )
            if not mobile:
                raise_param_error("mobile")
            if not sms_code:
                raise_param_error("sms_code")
            ret = verify_sms_code(app, user_id, mobile, sms_code, course_id)
            db.session.commit()
            resp = make_response(make_common_response(ret))
            return resp

    @app.route(path_prefix + "/get_profile", methods=["GET"])
    def get_profile():
        course_id = request.args.get("course_id", None)
        """
        get user profile
        ---
        tags:
            - user
        responses:
            200:
                description: Return user profile
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return message
                                data:
                                    type: object
                                    description: user profile

        """
        return make_common_response(
            get_user_profile_labels(app, request.user.user_id, course_id)
        )

    @app.route(path_prefix + "/update_profile", methods=["POST"])
    def update_profile():
        """
        update user information
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
                                    description: attribute key
                                value:
                                    type: string
                                    description: attribute value
                    course_id:
                        type: string
                        description: Course ID
        responses:
            200:
                description: update success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
        """
        profiles = request.get_json().get("profiles", None)
        course_id = request.get_json().get("course_id", None)
        if not profiles:
            raise_param_error("profiles")
        with app.app_context():
            ret = update_user_profile_with_lable(
                app,
                request.user.user_id,
                profiles,
                update_all=True,
                course_id=course_id,
            )
            db.session.commit()
            return make_common_response(ret)

    @app.route(path_prefix + "/upload_avatar", methods=["POST"])
    def upload_avatar():
        """
        Upload avatar
        ---
        tags:
            - user
        parameters:
            - in: formData
              name: avatar
              type: file
              required: true
              description: avatar file
        responses:
            200:
                description: upload success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    type: string
                                    description: avatar address
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
        summary: update wechat openid
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
                        description: wechat code
        responses:
            200:
                description: upload success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
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
    @bypass_token_validation
    @optional_token_validation
    def sumbit_feedback_api():
        """
        submit feedback
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
                    mail:
                        type: string
                        description: mail
                    feedback:
                        type: string
                        description: feedback content
        responses:
            200:
                description: submitted success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    type: integer
                                    description: feedback ID
            400:
                description: parameter error
        """
        user_id = getattr(request, "user", None)
        if user_id:
            user_id = user_id.user_id
        feedback = request.get_json().get("feedback", None)
        mail = request.get_json().get("mail", None)
        if not feedback:
            raise_param_error("feedback")
        return make_common_response(submit_feedback(app, user_id, feedback, mail))

    @app.route(path_prefix + "/send_mail_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def send_mail_code_api():
        """
        Send email Captcha
        ---
        tags:
           - user

        parameters:
          - in: body
            required: true
            schema:
              properties:
                mail:
                  type: string
                  description: mail
              required:
                - mobile
        responses:
            200:
                description: sent successfully
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: retrun message
                                data:
                                    description: mail captcha expire_in
                                    schema:
                                        properties:
                                            expire_in:
                                                type: integer
                                                description: expire in
            400:
                description: parameter error

        """
        mail = request.get_json().get("mail", None)
        if not mail:
            raise_param_error("mail")
        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr
        return make_common_response(send_email_code(app, mail, client_ip))

    @app.route(path_prefix + "/verify_mail_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def verify_mail_code_api():
        """
        Send verify email code
        ---
        tags:
            - user
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        mail:
                            type: string
                            description: mail
                        mail_code:
                            type: string
                            description: mail chekcode
                        course_id:
                            type: string
                            description: course id
        responses:
            200:
                description: user logs in success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
                                data:
                                    $ref: "#/components/schemas/UserToken"
            400:
                description: parameter error


        """
        with app.app_context():

            mail = request.get_json().get("mail", None)
            mail_code = request.get_json().get("mail_code", None)
            course_id = request.get_json().get("course_id", None)
            user_id = (
                None if getattr(request, "user", None) is None else request.user.user_id
            )
            if not mail:
                raise_param_error("mail")
            if not mail_code:
                raise_param_error("sms_code")
            ret = verify_mail_code(app, user_id, mail, mail_code, course_id)
            db.session.commit()
            resp = make_response(make_common_response(ret))
            return resp

    # set_user_password
    @app.route(path_prefix + "/set_user_password", methods=["POST"])
    # @bypass_token_validation
    def set_user_password_api():
        """
        Send set user password
        ---
        tags:
            - user
        parameters:
            -   in: body
                required: true
                schema:
                    properties:
                        mail:
                            type: string
                            description: mail
                        mobile:
                            type: string
                            description: mail chekcode
                        raw_password:
                            type: string
                            description: course id
        responses:
            200:
                description: user set password success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: return code
                                message:
                                    type: string
                                    description: return information
            400:
                description: parameter error
        """
        with app.app_context():
            mail = request.get_json().get("mail", None)
            mobile = request.get_json().get("mobile", None)
            raw_password = request.get_json().get("raw_password", None)
            if not mail and not mobile:
                raise_param_error("mail")
            if not raw_password:
                raise_param_error("password")
            return make_common_response(
                set_user_password(app, raw_password, mail, mobile)
            )

    # health check
    @app.route("/health", methods=["GET"])
    @bypass_token_validation
    def health():
        app.logger.info("health")
        return make_common_response("ok")

    return app
