from flask import Flask, request, make_response, current_app
from functools import wraps
import threading

from flaskr.service.common.models import raise_param_error, raise_error
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED
from flaskr.service.user.password_utils import (
    hash_password,
    verify_password,
    validate_password_strength,
)
from flaskr.service.user.models import AuthCredential
from flaskr.util.uuid import generate_id
from flaskr.service.user.repository import (
    find_credential,
    get_password_hash,
    set_password_hash,
    load_user_aggregate_by_identifier,
    list_credentials,
)
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from ..service.user.common import validate_user, update_user_info, verify_sms_code
from ..service.user.user import (
    generate_temp_user,
    update_user_open_id,
    upload_user_avatar,
)
from ..service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    send_email_code,
    send_sms_code,
)
from flaskr.service.user.verification_codes import consume_verification_code
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

    @app.route(path_prefix + "/ensure_admin_creator", methods=["POST"])
    def ensure_admin_creator():
        """
        Ensure admin creator permissions for the current user.
        ---
        tags:
            - user
        responses:
            200:
                description: ensure admin creator permissions
        """
        language = getattr(request.user, "language", None) or "en-US"
        ensure_admin_creator_and_demo_permissions(
            app,
            request.user.user_id,
            language,
            "admin",
        )
        db.session.commit()
        return make_common_response({"granted": True})

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

    @app.route(path_prefix + "/send_email_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def send_email_code_api():
        """
        Send email verification code
        ---
        tags:
           - user
        """
        email = request.get_json().get("email", None)
        language = request.get_json().get("language", None)
        if not email:
            raise_param_error("email")

        # Best-effort language override for the email subject.
        if language:
            try:
                set_language(language)
            except Exception:
                pass

        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr

        return make_common_response(send_email_code(app, email, client_ip, language))

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
            login_context = request.get_json().get("login_context", None)
            user_id = (
                None if getattr(request, "user", None) is None else request.user.user_id
            )
            if not mobile:
                raise_param_error("mobile")
            if not sms_code:
                raise_param_error("sms_code")
            ret = verify_sms_code(
                app,
                user_id,
                mobile,
                sms_code,
                course_id,
                language,
                login_context,
            )
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

    @app.route(path_prefix + "/oauth/google", methods=["GET"])
    @bypass_token_validation
    def google_oauth_start():
        provider = get_provider("google")
        metadata = {}
        redirect_uri = request.args.get("redirect_uri")
        if redirect_uri:
            metadata["redirect_uri"] = redirect_uri
        login_context = request.args.get("login_context")
        if login_context:
            metadata["login_context"] = login_context
        ui_language = request.args.get("language")
        if ui_language:
            metadata["language"] = ui_language
        result = provider.begin_oauth(app, metadata)
        dto = OAuthStartDTO(
            authorization_url=result["authorization_url"],
            state=result["state"],
        )
        return make_common_response(dto)

    @app.route(path_prefix + "/oauth/google/callback", methods=["GET"])
    @bypass_token_validation
    @optional_token_validation
    def google_oauth_callback():
        provider = get_provider("google")
        current_user = getattr(request, "user", None)
        current_user_id = None
        if current_user is not None:
            current_user_id = getattr(current_user, "user_id", None)

        callback_request = OAuthCallbackRequest(
            state=request.args.get("state"),
            code=request.args.get("code"),
            raw_request_args=request.args.to_dict(flat=True),
            current_user_id=current_user_id,
        )
        try:
            auth_result = provider.handle_oauth_callback(app, callback_request)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return make_common_response(auth_result.token)

    # -------- Password login routes --------

    @app.route(path_prefix + "/login_password", methods=["POST"])
    @bypass_token_validation
    def login_password():
        """
        Login with password
        ---
        tags:
            - user
        """
        identifier = request.get_json().get("identifier", None)
        password = request.get_json().get("password", None)
        language = request.get_json().get("language", None)
        if language:
            try:
                set_language(language)
            except Exception:
                pass
        if not identifier:
            raise_param_error("identifier")
        if not password:
            raise_param_error("password")
        from flaskr.service.user.auth.base import VerificationRequest

        provider = get_provider("password")
        vr = VerificationRequest(identifier=identifier, code=password)
        # TODO: Add rate-limiting and failed login attempt tracking
        # (record identifier, request.remote_addr, timestamp on failure)
        auth_result = provider.verify(app, vr)
        db.session.commit()
        return make_common_response(auth_result.token)

    @app.route(path_prefix + "/set_password", methods=["POST"])
    def set_password():
        """
        Set password for logged-in user (first time only)
        ---
        tags:
            - user
        """

        identifier = request.get_json().get("identifier", None)
        code = request.get_json().get("code", None)
        new_password = request.get_json().get("new_password", None)
        if not code:
            raise_param_error("code")
        if not new_password:
            raise_param_error("new_password")
        validate_password_strength(new_password)

        user = request.user
        user_bid = user.user_id

        # Find user's phone/email credential to get identifier
        creds = list_credentials(user_bid=user_bid)
        available_identifiers = []
        for c in creds:
            if c.provider_name in ("phone", "email") and c.identifier:
                normalized = (
                    c.identifier.lower() if c.provider_name == "email" else c.identifier
                )
                available_identifiers.append(normalized)

        selected_identifier = None
        if identifier:
            normalized = (
                identifier.strip().lower() if "@" in identifier else identifier.strip()
            )
            if normalized not in available_identifiers:
                # Avoid leaking whether another account exists for the identifier.
                raise_error("server.user.invalidCredentials")
            selected_identifier = normalized
        else:
            selected_identifier = (
                available_identifiers[0] if available_identifiers else None
            )

        if not selected_identifier:
            raise_param_error("identifier")

        # Reject if user already has a password credential (use change_password instead)
        pwd_cred = find_credential(
            provider_name="password", identifier=selected_identifier, user_bid=user_bid
        )
        if pwd_cred and get_password_hash(pwd_cred):
            raise_error("server.user.passwordAlreadySet")

        # Validate ownership by consuming a verification code for the chosen identifier.
        consume_verification_code(app, identifier=selected_identifier, code=code)

        subject_format = "email" if "@" in selected_identifier else "phone"

        if pwd_cred:
            set_password_hash(pwd_cred, hash_password(new_password))
        else:
            pwd_cred = AuthCredential(
                credential_bid=generate_id(app),
                user_bid=user_bid,
                provider_name="password",
                subject_id=selected_identifier,
                subject_format=subject_format,
                identifier=selected_identifier,
                raw_profile="",
                state=CREDENTIAL_STATE_VERIFIED,
                deleted=0,
            )
            db.session.add(pwd_cred)
            set_password_hash(pwd_cred, hash_password(new_password))

        db.session.commit()
        return make_common_response({"success": True})

    @app.route(path_prefix + "/change_password", methods=["POST"])
    def change_password():
        """
        Change password for logged-in user (requires old password)
        ---
        tags:
            - user
        """
        old_password = request.get_json().get("old_password", None)
        new_password = request.get_json().get("new_password", None)
        if not old_password:
            raise_param_error("old_password")
        if not new_password:
            raise_param_error("new_password")

        validate_password_strength(new_password)

        user = request.user
        user_bid = user.user_id

        # Find user's password credential
        creds = list_credentials(user_bid=user_bid, provider_name="password")
        if not creds:
            raise_error("server.user.invalidCredentials")

        pwd_cred = creds[0]
        current_hash = get_password_hash(pwd_cred)
        if not current_hash or not verify_password(old_password, current_hash):
            raise_error("server.user.invalidCredentials")

        set_password_hash(pwd_cred, hash_password(new_password))
        db.session.commit()
        return make_common_response({"success": True})

    @app.route(path_prefix + "/reset_password", methods=["POST"])
    @bypass_token_validation
    def reset_password():
        """
        Reset password via verification code
        ---
        tags:
            - user
        """

        identifier = request.get_json().get("identifier", None)
        code = request.get_json().get("code", None)
        new_password = request.get_json().get("new_password", None)
        if not identifier:
            raise_param_error("identifier")
        if not code:
            raise_param_error("code")
        if not new_password:
            raise_param_error("new_password")

        validate_password_strength(new_password)

        raw_identifier = identifier.strip()
        normalized_identifier = (
            raw_identifier.lower() if "@" in raw_identifier else raw_identifier
        )

        # Reset is only allowed for existing users. New users must go through
        # phone-code / Google login first.
        aggregate = load_user_aggregate_by_identifier(
            normalized_identifier, providers=["phone", "email"]
        )
        if not aggregate:
            raise_error("server.user.userNotFound")

        # Verify identity via verification code without creating/merging users.
        consume_verification_code(app, identifier=raw_identifier, code=code)

        user_bid = aggregate.user_bid
        subject_format = "email" if "@" in normalized_identifier else "phone"

        # Find or create password credential
        pwd_cred = find_credential(
            provider_name="password",
            identifier=normalized_identifier,
            user_bid=user_bid,
        )
        if pwd_cred:
            set_password_hash(pwd_cred, hash_password(new_password))
        else:
            pwd_cred = AuthCredential(
                credential_bid=generate_id(app),
                user_bid=user_bid,
                provider_name="password",
                subject_id=normalized_identifier,
                subject_format=subject_format,
                identifier=normalized_identifier,
                raw_profile="",
                state=CREDENTIAL_STATE_VERIFIED,
                deleted=0,
            )
            db.session.add(pwd_cred)
            set_password_hash(pwd_cred, hash_password(new_password))

        db.session.commit()
        return make_common_response({"success": True})

    # health check
    @app.route("/health", methods=["GET"])
    @bypass_token_validation
    def health():
        app.logger.info("health")
        return make_common_response("ok")

    return app
