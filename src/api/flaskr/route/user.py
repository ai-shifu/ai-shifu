"""Expose user HTTP routes."""

import contextlib
from functools import wraps

from flask import Flask, current_app, make_response, request

from flaskr.common.public_urls import resolve_request_origin
from flaskr.common.shifu_context import with_shifu_context
from flaskr.dao import db
from flaskr.i18n import _translations, set_language
from flaskr.service.common.dtos import OAuthStartDTO, UserToken
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.feedback.funs import submit_feedback
from flaskr.service.profile.api import merge_learner_profile_for_sign_in
from flaskr.service.profile.funcs import (
    get_user_profile_labels,
    update_user_profile_with_lable,
)
from flaskr.service.profile.learner_profile import (
    clear_learner_profile,
    get_learner_profile,
    replace_learner_profile,
)
from flaskr.service.profile.learner_profile_optimizer import optimize_learner_profile
from flaskr.service.profile.learner_profile_optimizer_admission import (
    learner_profile_optimization_admission,
)
from flaskr.service.profile.onboarding import (
    complete_profile_onboarding,
    get_profile_onboarding_status,
)
from flaskr.service.referral.service import extract_referral_post_auth_fields
from flaskr.service.user.auth import get_provider
from flaskr.service.user.auth.base import OAuthCallbackRequest, VerificationRequest
from flaskr.service.user.auth.providers.google import (
    resolve_state_return_origin,
)
from flaskr.service.user.captcha import (
    create_captcha_challenge,
    verify_captcha_code,
)
from flaskr.service.user.common import update_user_info, validate_user
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.onboarding import (
    ONBOARDING_VERSION,
    build_onboarding_status,
    complete_onboarding_scene,
)
from flaskr.service.user.password_utils import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from flaskr.service.user.post_auth import PostAuthContext, run_post_auth_extensions
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    find_credential,
    get_password_hash,
    list_credentials,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    set_password_hash,
)
from flaskr.service.user.user import (
    generate_temp_user,
    update_user_open_id,
    upload_user_avatar,
)
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    send_email_code,
    send_sms_code,
)
from flaskr.service.user.verification_codes import consume_verification_code
from flaskr.util.uuid import generate_id

from .common import by_pass_login_func, bypass_token_validation, make_common_response

_DEFAULT_SUPPORTED_RUNTIME_LANGUAGES = ("zh-CN", "en-US", "fr-FR")


def _request_json_object(parameter_name: str) -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise_param_error(parameter_name)
    return payload


def _reject_unknown_fields(
    payload: dict, *, allowed_fields: set[str], parameter_name: str
) -> None:
    if set(payload) - allowed_fields:
        raise_param_error(parameter_name)


def _normalize_runtime_language_code(language_code: str) -> str:
    normalized = str(language_code or "").strip().replace("_", "-")
    parts = [segment for segment in normalized.split("-") if segment]
    if not parts:
        return ""

    normalized_parts = [parts[0].lower()]
    for segment in parts[1:]:
        if len(segment) == 2 and segment.isalpha():
            normalized_parts.append(segment.upper())
        elif len(segment) == 4 and segment.isalpha():
            normalized_parts.append(segment.title())
        else:
            normalized_parts.append(segment)
    return "-".join(normalized_parts)


def _resolve_supported_runtime_language(raw_language: str | None) -> str | None:
    normalized_language = _normalize_runtime_language_code(raw_language or "")
    if not normalized_language:
        return None

    supported_languages = (
        tuple(_translations.keys()) or _DEFAULT_SUPPORTED_RUNTIME_LANGUAGES
    )
    normalized_language_lower = normalized_language.lower()
    for supported_language in supported_languages:
        if supported_language.lower() == normalized_language_lower:
            return supported_language

    primary_language = normalized_language_lower.split("-", 1)[0]
    for supported_language in supported_languages:
        if supported_language.lower().split("-", 1)[0] == primary_language:
            return supported_language

    return normalized_language


def _extract_request_language(payload: dict | None = None) -> str | None:
    raw_language = None
    if isinstance(payload, dict):
        language = payload.get("language")
        if language:
            raw_language = str(language).strip()

    if not raw_language:
        accept_language = request.headers.get("Accept-Language", "")
        if not accept_language:
            return None

        first_part = accept_language.split(",")[0].strip()
        if not first_part:
            return None
        raw_language = first_part.split(";")[0].strip()

    return _resolve_supported_runtime_language(raw_language)


def _apply_request_language(payload: dict | None = None) -> None:
    language = _extract_request_language(payload)
    if language:
        set_language(language)


def _resolve_runtime_language(user, payload: dict | None = None) -> str:
    """Prefer the current client language for this request without mutating the profile."""
    if payload is None and request.is_json:
        json_data = request.get_json(silent=True) or {}
        if isinstance(json_data, dict):
            payload = json_data
    return (
        _extract_request_language(payload) or getattr(user, "language", None) or "en-US"
    )


def _request_client_ip() -> str:
    if "X-Forwarded-For" in request.headers:
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return str(request.remote_addr or "").strip()


def _extract_referral_post_auth_fields(payload: dict) -> dict[str, str]:
    return extract_referral_post_auth_fields(
        payload,
        client_ip=_request_client_ip(),
        user_agent=request.headers.get("User-Agent"),
    )


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
            set_language(_resolve_runtime_language(user))
            request.user = user
        return f(*args, **kwargs)

    return decorated_function


def _best_effort_password_login_user(app: Flask):
    """Resolve the explicitly authenticated guest without blocking login."""
    token = request.headers.get("Token", None)
    if not token:
        return None

    try:
        return validate_user(app, str(token))
    except Exception:  # stale login tokens must not block recovery
        return None


def register_user_handler(app: Flask, path_prefix: str) -> Flask:
    @app.before_request
    def before_request():
        if request.path.startswith("/internal/"):
            return
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
        set_language(_resolve_runtime_language(user))
        request.user = user

    @app.route(path_prefix + "/info", methods=["GET"])
    def info():
        """Get user information.

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
        """Ensure admin creator permissions for the current user.

        ---
        tags:
            - user
        responses:
            200:
                description: ensure admin creator permissions
        """
        language = getattr(request.user, "language", None) or "en-US"
        creator_granted_now = ensure_admin_creator_and_demo_permissions(
            app,
            request.user.user_id,
            language,
            "admin",
        )
        db.session.commit()
        run_post_auth_extensions(
            app,
            PostAuthContext(
                user_id=request.user.user_id,
                source="admin_creator",
                login_context="admin",
                created_new_user=False,
                creator_granted_now=creator_granted_now,
                language=language,
            ),
        )
        return make_common_response({"granted": True})

    @app.route(path_prefix + "/onboarding/status", methods=["GET"])
    def onboarding_status():
        return make_common_response(
            build_onboarding_status(
                app,
                request.user.user_id,
                getattr(request.user, "language", None),
            )
        )

    @app.route(path_prefix + "/onboarding/complete", methods=["POST"])
    def complete_onboarding():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}
        return make_common_response(
            complete_onboarding_scene(
                app,
                request.user.user_id,
                scene_key=payload.get("scene_key"),
                version=payload.get("version") or ONBOARDING_VERSION,
                trigger_source=payload.get("trigger_source"),
                status=payload.get("status"),
            )
        )

    @app.route(path_prefix + "/update_info", methods=["POST"])
    def update_info():
        """Update user information.

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

    @app.route(path_prefix + "/profile-onboarding", methods=["GET"])
    def profile_onboarding_status_api():
        """Get platform-level profile onboarding state for current user.

        ---
        tags:
            - user
        responses:
            200:
                description: onboarding config and current user state
        """
        return make_common_response(
            get_profile_onboarding_status(app, user_id=request.user.user_id)
        )

    @app.route(path_prefix + "/profile-onboarding/complete", methods=["POST"])
    def complete_profile_onboarding_api():
        """Complete or skip platform-level profile onboarding.

        ---
        tags:
            - user
        responses:
            200:
                description: onboarding completion result
        """
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("profile_onboarding")
        result = complete_profile_onboarding(
            app,
            user_id=request.user.user_id,
            skipped=bool(payload.get("skipped", False)),
            variables=payload.get("variables") or {},
        )
        db.session.commit()
        return make_common_response(result)

    @app.route(path_prefix + "/learner-profile", methods=["GET"])
    def learner_profile_api():
        """Return the current user's canonical learning profile."""
        return make_common_response(get_learner_profile(user_id=request.user.user_id))

    @app.route(path_prefix + "/learner-profile", methods=["PUT"])
    def update_learner_profile_api():
        """Replace the current user's canonical learning profile."""
        payload = _request_json_object("learner_profile")
        _reject_unknown_fields(
            payload,
            allowed_fields={"learner_profile", "nickname"},
            parameter_name="learner_profile",
        )
        learner_profile = payload.get("learner_profile")
        if not isinstance(learner_profile, str):
            raise_param_error("learner_profile")
        nickname = payload.get("nickname")
        if "nickname" in payload and not isinstance(nickname, str):
            raise_param_error("nickname")
        return make_common_response(
            replace_learner_profile(
                app,
                user_id=request.user.user_id,
                learner_profile=learner_profile,
                nickname=nickname,
            )
        )

    @app.route(path_prefix + "/learner-profile", methods=["DELETE"])
    def clear_learner_profile_api():
        """Clear the profile while keeping profile-v2 handled."""
        return make_common_response(clear_learner_profile(user_id=request.user.user_id))

    @app.route(path_prefix + "/learner-profile/optimize", methods=["POST"])
    def optimize_learner_profile_api():
        """Return an LLM-optimized draft without saving profile state."""
        payload = _request_json_object("learner_profile")
        _reject_unknown_fields(
            payload,
            allowed_fields={"learner_profile"},
            parameter_name="learner_profile",
        )
        learner_profile = payload.get("learner_profile")
        if not isinstance(learner_profile, str):
            raise_param_error("learner_profile")
        with learner_profile_optimization_admission(
            app,
            user_id=request.user.user_id,
        ):
            result = optimize_learner_profile(
                app,
                user_id=request.user.user_id,
                learner_profile=learner_profile,
                output_language=getattr(request.user, "language", None),
            )
        return make_common_response(result)

    @app.route(path_prefix + "/require_tmp", methods=["POST"])
    @bypass_token_validation
    @with_shifu_context()
    def require_tmp():
        """Temp login user.

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
        parsed_payload = request.get_json(silent=True)
        payload = parsed_payload if isinstance(parsed_payload, dict) else {}
        tmp_id = payload.get("temp_id", None)
        source = str(payload.get("source") or "web").strip() or "web"
        wx_code = payload.get("wxcode", None)
        language = payload.get("language") or "en-US"
        masked_wx_code = None
        if isinstance(wx_code, str) and wx_code:
            masked_wx_code = f"***{wx_code[-4:]}" if len(wx_code) > 4 else "***"
        app.logger.info(
            "require_tmp tmp_id: %s, source: %s, wx_code: %s",
            tmp_id,
            source,
            masked_wx_code,
        )
        if not tmp_id:
            raise_param_error("temp_id")
        user_token = generate_temp_user(app, tmp_id, source, wx_code, language)
        return make_response(make_common_response(user_token))

    @app.route(path_prefix + "/captcha", methods=["GET"])
    @bypass_token_validation
    def captcha_api():
        """Create image captcha.

        ---
        tags:
           - user
        """
        _apply_request_language()
        return make_common_response(create_captcha_challenge(app))

    @app.route(path_prefix + "/captcha/verify", methods=["POST"])
    @bypass_token_validation
    def captcha_verify_api():
        """Verify image captcha and return one-time ticket.

        ---
        tags:
           - user
        """
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        _apply_request_language(payload)
        captcha_id = payload.get("captcha_id", None)
        captcha_code = payload.get("captcha_code", None)
        if not captcha_id:
            raise_param_error("captcha_id")
        if not captcha_code:
            raise_param_error("captcha_code")
        return make_common_response(verify_captcha_code(app, captcha_id, captcha_code))

    # Flasgger parses `parameters:` below as a YAML key. D405 would capitalize
    # the key and remove the OpenAPI field, D406 would remove its colon, and
    # D407 would insert a dashed underline; each fix breaks the published API
    # specification.
    @app.route(path_prefix + "/send_sms_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def send_sms_code_api():
        """Send SMS Captcha.

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
                captcha_ticket:
                  type: string
                  description: one-time image captcha ticket
              required:
                - mobile
                - captcha_ticket
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

        """  # noqa: D405, D406, D407
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        _apply_request_language(payload)
        mobile = normalize_phone_identifier(payload.get("mobile", None))
        captcha_ticket = payload.get("captcha_ticket", None)
        if not mobile:
            raise_param_error("mobile")
        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr
        return make_common_response(
            send_sms_code(app, mobile, client_ip, captcha_ticket)
        )

    @app.route(path_prefix + "/console_send_sms_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def console_send_sms_code_api():
        """Send SMS verification code for console clients without image captcha.

        ---
        tags:
           - user
        """
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        _apply_request_language(payload)
        mobile = normalize_phone_identifier(payload.get("mobile", None))
        if not mobile:
            raise_param_error("mobile")
        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr
        return make_common_response(
            send_sms_code(app, mobile, client_ip, require_captcha=False)
        )

    @app.route(path_prefix + "/send_email_code", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def send_email_code_api():
        """Send email verification code.

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
            with contextlib.suppress(Exception):
                set_language(language)

        if "X-Forwarded-For" in request.headers:
            client_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            client_ip = request.remote_addr

        return make_common_response(send_email_code(app, email, client_ip, language))

    def _handle_sms_login():
        with app.app_context():
            payload = request.get_json(silent=True)
            payload = payload if isinstance(payload, dict) else {}
            mobile = normalize_phone_identifier(payload.get("mobile", None))
            sms_code = payload.get("sms_code", None)
            course_id = payload.get("course_id", None)
            language = payload.get("language", None)
            login_context = payload.get("login_context", None)
            referral_fields = _extract_referral_post_auth_fields(payload)
            current_user = getattr(request, "user", None)
            # Only pass an anonymous/guest token through SMS login so temporary
            # learning records can be claimed. If a real authenticated account
            # reaches the login page and verifies another phone number, this
            # endpoint must behave as login, not implicit phone rebinding.
            user_id = None
            if current_user is not None and not (
                getattr(current_user, "mobile", "")
                or getattr(current_user, "email", "")
            ):
                user_id = current_user.user_id
            if not mobile:
                raise_param_error("mobile")
            if not sms_code:
                raise_param_error("sms_code")
            provider = get_provider("phone")
            auth_result = provider.verify(
                app,
                VerificationRequest(
                    identifier=mobile,
                    code=sms_code,
                    metadata={
                        "user_id": user_id,
                        "course_id": course_id,
                        "language": language,
                        "login_context": login_context,
                    },
                ),
            )
            db.session.commit()
            run_post_auth_extensions(
                app,
                PostAuthContext(
                    user_id=auth_result.user.user_id,
                    source="sms",
                    login_context=login_context,
                    created_new_user=bool(auth_result.is_new_user),
                    creator_granted_now=bool(
                        auth_result.metadata.get("creator_granted_now")
                    ),
                    language=language or getattr(auth_result.user, "language", None),
                    **referral_fields,
                ),
            )
            return make_response(make_common_response(auth_result.token))

    @app.route(path_prefix + "/login_sms", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def login_sms_api():
        """Login through SMS verification code for web clients.

        ---
        tags:
           - user
        """
        return _handle_sms_login()

    @app.route(path_prefix + "/get_profile", methods=["GET"])
    def get_profile():
        """Get user profile.

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
        """Update user profile.

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
        """Upload avatar.

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
    @with_shifu_context()
    def update_wechat_openid():
        """Update Wechat OpenID.

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
        app.logger.info("update_wechat_openid code: %s", code)
        if not code:
            raise_param_error("wxcode")
        return make_common_response(
            update_user_open_id(app, request.user.user_id, code)
        )

    @app.route(path_prefix + "/submit-feedback", methods=["POST"])
    @bypass_token_validation
    @optional_token_validation
    def sumbit_feedback_api():
        """Submit feedback.

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
    @optional_token_validation
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
        # Every header here is attacker-controllable — the edge nginx passes
        # inbound X-Forwarded-* through, and Origin is forwarded unchanged — so
        # the origin alone cannot decide where the authorization code is sent.
        # It is paired with the session that started the flow, and the callback
        # refuses to hand the code back unless the same session presents it.
        metadata["origin"] = resolve_request_origin()
        initiator = getattr(request, "user", None)
        metadata["initiator_user_id"] = str(
            getattr(initiator, "user_id", "") or ""
        ).strip()
        result = provider.begin_oauth(app, metadata)
        dto = OAuthStartDTO(
            authorization_url=result["authorization_url"],
            state=result["state"],
        )
        return make_common_response(dto)

    @app.route(path_prefix + "/oauth/google/callback-origin", methods=["GET"])
    @bypass_token_validation
    def google_oauth_callback_origin():
        """Resolve which domain a pending Google login should return to.

        Every domain shares one Google callback, so the page that receives it
        asks here whether the code belongs to a different domain and should be
        forwarded there. Returns an empty origin when the login started on this
        domain or when the recorded origin is no longer allowed.
        ---
        tags:
            - user
        """
        origin = resolve_state_return_origin(app, request.args.get("state"))
        return make_common_response({"origin": origin})

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
        run_post_auth_extensions(
            app,
            PostAuthContext(
                user_id=auth_result.user.user_id,
                source="google",
                login_context=auth_result.metadata.get("login_context"),
                created_new_user=bool(auth_result.is_new_user),
                creator_granted_now=bool(
                    auth_result.metadata.get("creator_granted_now")
                ),
                language=auth_result.metadata.get("language")
                or getattr(auth_result.user, "language", None),
            ),
        )
        return make_common_response(auth_result.token)

    # -------- Password login routes --------

    @app.route(path_prefix + "/login_password", methods=["POST"])
    @bypass_token_validation
    def login_password():
        """Login with password.

        ---
        tags:
            - user
        """
        identifier = request.get_json().get("identifier", None)
        password = request.get_json().get("password", None)
        language = request.get_json().get("language", None)
        if language:
            with contextlib.suppress(Exception):
                set_language(language)
        if not identifier:
            raise_param_error("identifier")
        if not password:
            raise_param_error("password")
        provider = get_provider("password")
        vr = VerificationRequest(
            identifier=identifier,
            code=password,
            metadata={"remote_addr": request.remote_addr or ""},
        )
        auth_result = provider.verify(app, vr)
        current_user = _best_effort_password_login_user(app)
        current_user_id = (
            getattr(current_user, "user_id", None) if current_user is not None else None
        )
        if current_user_id and current_user_id != auth_result.user.user_id:
            merge_learner_profile_for_sign_in(
                source_user_id=current_user_id,
                target_user_id=auth_result.user.user_id,
            )
            refreshed = load_user_aggregate(auth_result.user.user_id)
            if not refreshed:
                raise_error("USER.USER_NOT_FOUND")
            refreshed_user = build_user_info_from_aggregate(refreshed)
            auth_result.user = refreshed_user
            auth_result.token = UserToken(
                userInfo=refreshed_user,
                token=auth_result.token.token,
            )
        db.session.commit()
        run_post_auth_extensions(
            app,
            PostAuthContext(
                user_id=auth_result.user.user_id,
                source="password",
                login_context=None,
                created_new_user=bool(auth_result.is_new_user),
                creator_granted_now=bool(
                    auth_result.metadata.get("creator_granted_now")
                ),
                language=language or getattr(auth_result.user, "language", None),
            ),
        )
        return make_common_response(auth_result.token)

    @app.route(path_prefix + "/set_password", methods=["POST"])
    def set_password():
        """Set password for logged-in user (first time only).

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
                    c.identifier.lower()
                    if c.provider_name == "email"
                    else normalize_phone_identifier(c.identifier)
                )
                available_identifiers.append(normalized)

        selected_identifier = None
        if identifier:
            normalized = (
                identifier.strip().lower()
                if "@" in identifier
                else normalize_phone_identifier(identifier)
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
        """Change password for logged-in user (requires old password).

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
        """Reset password via verification code.

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
            raw_identifier.lower()
            if "@" in raw_identifier
            else normalize_phone_identifier(raw_identifier)
        )

        # Reset is only allowed for existing users. New users must go through
        # phone-code / Google login first.
        aggregate = load_user_aggregate_by_identifier(
            normalized_identifier, providers=["phone", "email"]
        )
        if not aggregate:
            raise_error("server.user.userNotFound")

        # Verify identity via verification code without creating/merging users.
        consume_verification_code(app, identifier=normalized_identifier, code=code)

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
