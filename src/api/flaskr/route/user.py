from flask import Flask, request, make_response, current_app
from functools import wraps
import threading

from flaskr.service.common.models import raise_param_error
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from ..service.user import (
    validate_user,
    update_user_info,
    generate_temp_user,
    generation_img_chk,
    send_sms_code,
    send_email_code,
    verify_sms_code,
    verify_mail_code,
    upload_user_avatar,
    update_user_open_id,
)
from ..service.feedback.funs import submit_feedback
from ..service.user.auth import get_provider
from ..service.user.auth.base import OAuthCallbackRequest
from ..service.common.dtos import OAuthStartDTO
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
    @app.before_request
    def before_request():
        if (
            request.endpoint
            in [
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
                    name:
                        type: string
                        description: name
                    email:
                        type: string
                        description: email
                    mobile:
                        type: string
                        description: mobile
                    language:
                        type: string
                        description: language
                    avatar:
                        type: string
                        description: avatar
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
                                data:
                                    $ref: "#/components/schemas/UserInfo"
        """
        email = request.get_json().get("email", None)
        name = request.get_json().get("name", None)
        mobile = request.get_json().get("mobile", None)
        language = request.get_json().get("language", None)
        avatar = request.get_json().get("avatar", None)
        return make_common_response(
            update_user_info(app, request.user, name, email, mobile, language, avatar)
        )

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
            language = request.get_json().get("language", None)
            user_id = (
                None if getattr(request, "user", None) is None else request.user.user_id
            )
            if not mobile:
                raise_param_error("mobile")
            if not sms_code:
                raise_param_error("sms_code")
            ret = verify_sms_code(app, user_id, mobile, sms_code, course_id, language)
            db.session.commit()
            resp = make_response(make_common_response(ret))
            return resp

    @app.route(path_prefix + "/get_profile", methods=["GET"])
    def get_profile():
        """
        get user profile
        ---
        tags:
            - user
        parameters:
            - in: query
              name: course_id
              in: query
              type: string
              description: course id
              required: true
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
                                    $ref: "#/components/schemas/UserProfileLabelDTO"

        """
        course_id = request.args.get("course_id", None)
        if not course_id:
            raise_param_error("course_id")
        return make_common_response(
            get_user_profile_labels(app, request.user.user_id, course_id)
        )

    @app.route(path_prefix + "/update_profile", methods=["POST"])
    def update_profile():
        """
        update user profile
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
                                data:
                                    type: object
                                    description: user profile
                                    properties:
                                        $ref: "#/components/schemas/UserProfileLabelDTO"
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
            ret = get_user_profile_labels(app, request.user.user_id, course_id)
            return make_common_response(ret.__json__())

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
        language = request.get_json().get("language", None)
        if not mail:
            raise_param_error("mail")
        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr
        return make_common_response(send_email_code(app, mail, client_ip, language))

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
                        language:
                            type: string
                            description: language
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
            language = request.get_json().get("language", None)
            if not mail:
                raise_param_error("mail")
            if not mail_code:
                raise_param_error("mail_code")
            ret = verify_mail_code(app, user_id, mail, mail_code, course_id, language)
            db.session.commit()
            resp = make_response(make_common_response(ret))
            return resp

    @app.route(path_prefix + "/oauth/google", methods=["GET"])
    @bypass_token_validation
    def google_oauth_start():
        provider = get_provider("google")
        metadata = {}
        redirect_uri = request.args.get("redirect_uri")
        if redirect_uri:
            metadata["redirect_uri"] = redirect_uri
        result = provider.begin_oauth(app, metadata)
        dto = OAuthStartDTO(
            authorization_url=result["authorization_url"],
            state=result["state"],
        )
        return make_common_response(dto)

    @app.route(path_prefix + "/oauth/google/callback", methods=["GET"])
    @bypass_token_validation
    def google_oauth_callback():
        provider = get_provider("google")
        callback_request = OAuthCallbackRequest(
            state=request.args.get("state"),
            code=request.args.get("code"),
            raw_request_args=request.args.to_dict(flat=True),
        )
        try:
            auth_result = provider.handle_oauth_callback(app, callback_request)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return make_common_response(auth_result.token)

    # health check
    @app.route("/health", methods=["GET"])
    @bypass_token_validation
    def health():
        app.logger.info("health")
        return make_common_response("ok")

    return app
