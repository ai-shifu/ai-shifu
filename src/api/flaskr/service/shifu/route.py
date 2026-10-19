"""Shifu route.

This module contains route functions for shifu.
use restful api to manage shifu.
will be auto registered by flaskr.framework.plugin.inject.inject
includes:
    - get shifu list
    - create shifu
    - get shifu detail
    - save shifu detail
    - mark favorite shifu
    - publish shifu
    - preview shifu
    - reorder outline tree
    - create outline
    - modify outline
    - get outline info
    - delete outline
    - get outline tree
    - get block list
    - save blocks
    - add block
    - upload file
    - upload url
    - get video info

Author: yfge
Date: 2025-08-07
"""

import contextlib
import json
import re
from collections.abc import Callable, Generator
from enum import Enum
from functools import wraps

from flask import (
    Flask,
    current_app,
    g,
    has_request_context,
    request,
)
from flaskr.api.langfuse import (  # noqa: F401 -- re-exported names and patch targets
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm.model_selection import (  # noqa: F401 -- re-exported names and patch targets
    resolve_course_selection,
    selection_metadata,
    selection_model,
)
from flaskr.common.config import get_config
from flaskr.common.public_urls import resolve_public_origin
from flaskr.common.shifu_context import (
    with_shifu_context,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.framework.plugin.inject import inject
from flaskr.i18n import (  # noqa: F401 -- re-exported names and patch targets
    _,
    get_current_language,
    set_language,
)
from flaskr.route.common import (  # noqa: F401 -- re-exported names and patch targets
    bypass_token_validation,
    fmt,
    make_common_response,
)
from flaskr.service.billing.admission import admit_creator_usage
from flaskr.service.billing.api import (
    admit_creator_preview_usage,
    assert_creator_debug_allowed,
)
from flaskr.service.common.models import (  # noqa: F401 -- re-exported names and patch targets
    ERROR_CODE,
    raise_error,
    raise_param_error,
)
from flaskr.service.common.server_analytics import track_external_client_event
from flaskr.service.common.session_attribution import (
    get_session_skill_attribution_by_reference,
)
from flaskr.service.common.skill_request_analytics import has_skill_request_analytics
from flaskr.service.learn.ask_provider_langfuse import (
    stream_provider_with_langfuse,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.service.learn.langfuse_naming import (  # noqa: F401 -- re-exported names and patch targets
    build_langfuse_generation_name,
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
)
from flaskr.service.shifu.admin_operations.route import (
    register_admin_operations_routes,
)
from flaskr.service.shifu.ask_provider_registry import (  # noqa: F401 -- re-exported names and patch targets
    get_ask_provider_metadata,
    validate_ask_provider_specific_config,
)
from flaskr.service.shifu.ask_routes import (
    register_shifu_ask_routes,
)
from flaskr.service.shifu.course_routes import (
    register_shifu_course_archive_routes,
    register_shifu_course_detail_routes,
    register_shifu_course_export_routes,
    register_shifu_course_list_routes,
    register_shifu_course_preview_routes,
)
from flaskr.service.shifu.demo_courses import is_builtin_demo_shifu
from flaskr.service.shifu.mdflow_routes import (
    register_shifu_mdflow_routes,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.service.shifu.outline_routes import (
    register_shifu_outline_routes,
    register_shifu_outline_tree_routes,
)
from flaskr.service.shifu.permission_routes import (
    register_shifu_permission_routes,
)
from flaskr.service.shifu.permissions import (  # noqa: F401 -- re-exported names and patch targets
    _auth_types_to_permissions,
    _normalize_auth_types,
)
from flaskr.service.shifu.resource_routes import (
    register_shifu_resource_routes,
)
from flaskr.service.shifu.shifu_draft_funcs import (  # noqa: F401 -- re-exported names and patch targets
    SUPPORTED_ASK_ENABLED_STATUSES,
    SUPPORTED_ASK_PROVIDER_MODES,
    SUPPORTED_ASK_PROVIDERS,
    archive_shifu,
    create_shifu_draft,
    get_latest_shifu_draft,
    get_shifu_draft_info,
    get_shifu_draft_list,
    normalize_ask_provider_config,
    save_shifu_draft_info,
    unarchive_shifu,
)
from flaskr.service.shifu.shifu_history_manager import (
    get_shifu_draft_meta,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.service.shifu.shifu_import_export_funcs import (
    export_shifu,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.service.shifu.shifu_mdflow_funcs import (  # noqa: F401 -- re-exported names and patch targets
    get_shifu_mdflow,
    get_shifu_mdflow_history,
    get_shifu_mdflow_history_version_detail,
    parse_shifu_mdflow,
    restore_shifu_mdflow_history_version,
    save_shifu_mdflow,
)
from flaskr.service.shifu.shifu_outline_funcs import (  # noqa: F401 -- re-exported names and patch targets
    create_outline,
    create_outlines_batch,
    delete_unit,
    get_outline_tree,
    get_unit_by_id,
    modify_unit,
    reorder_outline_siblings,
    reorder_outline_tree,
)
from flaskr.service.shifu.shifu_permission_funcs import (  # noqa: F401 -- re-exported names and patch targets
    grant_shifu_permissions,
    remove_shifu_permission,
)
from flaskr.service.shifu.shifu_publish_funcs import (  # noqa: F401 -- re-exported names and patch targets
    preview_shifu_draft,
    publish_shifu_draft,
)
from flaskr.service.shifu.tts_routes import (
    register_shifu_tts_routes,
)
from flaskr.service.shifu.utils import get_shifu_creator_bid
from flaskr.service.user.common import (
    validate_user,  # noqa: F401 -- re-exported names and patch targets
)
from flaskr.service.user.repository import (  # noqa: F401 -- re-exported names and patch targets
    load_user_aggregate,
)
from flaskr.service.user.utils import (  # noqa: F401 -- re-exported names and patch targets
    get_user_language,
)

from .funcs import (  # noqa: F401 -- re-exported names and patch targets
    get_video_info,
    mark_or_unmark_favorite_shifu,
    shifu_permission_verification,
    upload_file,
    upload_url,
)


@contextlib.contextmanager
def _external_client_course_event(app: Flask, operation: str) -> Generator[None]:
    """Report one attributed course operation without changing its outcome."""
    if has_skill_request_analytics():
        # The request lifecycle owns exactly one terminal event for this client.
        yield
        return
    attribution = get_session_skill_attribution_by_reference(
        app,
        reference=str(
            getattr(g, "authenticated_session_attribution", "") or ""
        ).strip(),
    )
    track_external_client_event(
        app,
        event_name=f"external_course_{operation}_started",
        attribution=attribution,
    )
    try:
        yield
    except Exception:
        track_external_client_event(
            app,
            event_name=f"external_course_{operation}_failed",
            attribution=attribution,
        )
        raise
    track_external_client_event(
        app,
        event_name=f"external_course_{operation}_completed",
        attribution=attribution,
    )


class ShifuPermission(Enum):
    """Enumerate permission levels for course operations."""

    VIEW = "view"
    EDIT = "edit"
    PUBLISH = "publish"


MAX_CONTACT_LENGTH = 320
PHONE_PATTERN = re.compile(r"^\d{11}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class ShifuTokenValidation:
    """Shifu token validation decorator if is_creator is true, only verify creator permission and skip shifu-specific verification."""

    def __init__(
        self,
        permission: ShifuPermission = ShifuPermission.VIEW,
        is_creator: bool = False,
    ) -> None:
        """Store the required permission and creator-only validation mode."""
        self.permission = permission
        self.is_creator = is_creator

    def __call__(self, f: object) -> Callable:
        """Validate token permissions and optional creator status before invoking the route."""

        @wraps(f)
        def decorated_function(*args: object, **kwargs: object) -> object:
            token = request.cookies.get("token", None)
            if not token:
                token = request.args.get("token", None)
            if not token:
                token = request.headers.get("Token", None)
            if not token and request.method.upper() == "POST" and request.is_json:
                token = request.get_json().get("token", None)

            # If is_creator is True, only verify creator permission and skip shifu-specific verification
            if self.is_creator:
                if not request.user.is_creator:
                    raise_error("server.shifu.noPermission")
                return f(*args, **kwargs)

            shifu_bid = request.view_args.get("shifu_bid", None)
            if not shifu_bid:
                shifu_bid = request.view_args.get("shifu_id", None)
            if not shifu_bid:
                shifu_bid = request.args.get("shifu_bid", None)
            if not shifu_bid:
                shifu_bid = request.args.get("shifu_id", None)
            if not shifu_bid and request.method.upper() == "POST" and request.is_json:
                shifu_bid = request.get_json().get("shifu_bid", None)
                if not shifu_bid:
                    shifu_bid = request.get_json().get("shifu_id", None)

            if not token:
                raise_param_error("token is required")
            if not shifu_bid or not str(shifu_bid).strip():
                raise_param_error("shifu_bid is required")

            user_id = request.user.user_id

            app = current_app._get_current_object()
            has_permission = shifu_permission_verification(
                app, user_id, shifu_bid, self.permission.value
            )
            if not has_permission:
                raise_error("server.shifu.noPermission")

            return f(*args, **kwargs)

        return decorated_function


def _get_request_base_url() -> str:
    """Determine the base URL for frontend links."""
    return resolve_public_origin()


def _resolve_publish_base_url(app: Flask) -> str:
    """Resolve the publish/preview base URL for a shifu.

    When the request arrives through a verified custom domain that domain takes
    precedence regardless of who owns the shifu, so every creator on that
    domain sees the same base URL for publishing and previews. Falls back to
    the shifu owner's custom domain, then to the default public origin.
    """
    host = None
    if has_request_context():
        host = str(request.headers.get("X-Forwarded-Host", "") or "").strip()
        if host:
            host = host.split(",", 1)[0].strip()
        else:
            host = str(getattr(request, "host", "") or "").strip()
    if host:
        try:
            from flaskr.service.billing.api import (
                resolve_creator_bid_by_host,
                resolve_effective_custom_origin,
            )

            domain_creator_bid = resolve_creator_bid_by_host(app, host)
            if domain_creator_bid:
                domain_origin = resolve_effective_custom_origin(app, domain_creator_bid)
                if domain_origin:
                    return domain_origin
        except Exception:
            app.logger.exception(
                "Failed to resolve custom domain from request host; host=%s",
                host,
            )

    from flaskr.common.shifu_context import (
        get_shifu_creator_bid as get_context_creator_bid,
    )

    creator_bid = get_context_creator_bid()
    if creator_bid:
        try:
            from flaskr.service.billing.api import (
                resolve_effective_custom_origin,
            )

            custom_origin = resolve_effective_custom_origin(app, creator_bid)
            if custom_origin:
                return custom_origin
        except Exception:
            app.logger.exception(
                "Failed to resolve custom domain for publish link; creator_bid=%s",
                creator_bid,
            )
    return _get_request_base_url()


def _get_login_methods_enabled() -> set[str]:
    """Resolve enabled login methods from configuration."""
    raw = get_config("LOGIN_METHODS_ENABLED", "phone")
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw).split(",")
    methods = {str(item).strip().lower() for item in items if str(item).strip()}
    if "google" in methods:
        methods.add("email")
    return methods


def _normalize_contact_type(raw_type: str) -> str:
    """Normalize the incoming contact type value."""
    return (raw_type or "").strip().lower()


def _normalize_contacts(raw_contacts: object) -> list[str]:
    """Split and normalize contact identifiers from request payloads."""
    if isinstance(raw_contacts, str):
        items = re.split(r"[,\uFF0C\n]", raw_contacts)
    elif isinstance(raw_contacts, (list, tuple, set)):
        items = list(raw_contacts)
    else:
        items = []
    normalized = []
    for item in items:
        if item is None:
            continue
        trimmed = str(item).strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _validate_contacts(contact_type: str, contacts: list[str]) -> list[str]:
    """Validate and deduplicate contact identifiers."""
    normalized: list[str] = []
    seen: set[str] = set()
    for contact in contacts:
        if not contact or len(contact) > MAX_CONTACT_LENGTH:
            raise_param_error("contact")
        candidate = contact.lower() if contact_type == "email" else contact
        if candidate in seen:
            continue
        seen.add(candidate)
        if contact_type == "phone":
            if not PHONE_PATTERN.match(contact):
                raise_param_error("mobile")
        elif contact_type == "email" and not EMAIL_PATTERN.match(candidate):
            raise_param_error("email")
        normalized.append(candidate)
    return normalized


def _parse_ask_provider_config(raw_value: object) -> dict | None:
    """Parse and validate ask_provider_config from request payload."""
    if raw_value is None:
        return None

    parsed = raw_value
    if isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if not trimmed:
            parsed = {}
        else:
            try:
                parsed = json.loads(trimmed)
            except json.JSONDecodeError:
                raise_param_error("ask_provider_config")

    if not isinstance(parsed, dict):
        raise_param_error("ask_provider_config")

    provider = parsed.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower()
        if provider and provider not in SUPPORTED_ASK_PROVIDERS:
            raise_param_error("ask_provider_config.provider")

    mode = parsed.get("mode")
    if mode is not None:
        mode = str(mode).strip().lower()
        if mode and mode not in SUPPORTED_ASK_PROVIDER_MODES:
            raise_param_error("ask_provider_config.mode")

    if "config" in parsed and not isinstance(parsed.get("config"), dict):
        raise_param_error("ask_provider_config.config")

    normalized = normalize_ask_provider_config(parsed)
    is_valid, field = validate_ask_provider_specific_config(
        normalized.get("provider", ""),
        normalized.get("config", {}),
    )
    if not is_valid:
        raise_param_error(f"ask_provider_config.config.{field or 'invalid'}")

    return normalized


@inject
def register_shifu_routes(app: Flask, path_prefix: str = "/api/shifu") -> Flask:
    """Register shifu routes."""
    app.logger.info("register shifu routes %s", path_prefix)

    def _admit_creator_debug_usage(raw_shifu_bid: object) -> str:
        request_user = getattr(request, "user", None)
        user_bid = str(getattr(request_user, "user_id", "") or "").strip()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        if not isinstance(raw_shifu_bid, str) or not raw_shifu_bid.strip():
            raise_param_error("shifu_bid is required")
        shifu_bid = raw_shifu_bid.strip()
        if not shifu_permission_verification(
            app, user_bid, shifu_bid, ShifuPermission.EDIT.value
        ):
            raise_error("server.shifu.noPermission")
        creator_bid = get_shifu_creator_bid(app, shifu_bid)
        if not creator_bid:
            raise_error("server.shifu.shifuNotFound")
        # Resolve the payer from the authorized course, never from client fields
        # or the caller's teacher role. Settings previews cannot opt out of billing.
        assert_creator_debug_allowed(app, creator_bid)
        admit_creator_usage(
            app,
            creator_bid=creator_bid,
            shifu_bid=shifu_bid,
            usage_scene=BILL_USAGE_SCENE_DEBUG,
        )
        return shifu_bid

    def _admit_creator_preview_usage_for_shifu(shifu_bid: str) -> None:
        if is_builtin_demo_shifu(app, shifu_bid):
            return
        admit_creator_preview_usage(app, shifu_bid=shifu_bid)

    def _require_shifu_owner(shifu_bid: str) -> str:
        """Ensure the current user is the shifu owner and a creator."""
        user_id = request.user.user_id
        if not getattr(request.user, "is_creator", False):
            raise_error("server.shifu.noPermission")
        creator_bid = get_shifu_creator_bid(app, shifu_bid)
        if not creator_bid:
            raise_error("server.shifu.shifuNotFound")
        if creator_bid != user_id:
            raise_error("server.shifu.noPermission")
        return user_id

    register_shifu_course_list_routes(app, path_prefix)

    register_admin_operations_routes(app, path_prefix=path_prefix)

    register_shifu_course_archive_routes(app, path_prefix)
    register_shifu_permission_routes(
        app, path_prefix, _require_shifu_owner=_require_shifu_owner
    )
    register_shifu_course_detail_routes(app, path_prefix)
    register_shifu_course_preview_routes(
        app,
        path_prefix,
        _admit_creator_preview_usage_for_shifu=_admit_creator_preview_usage_for_shifu,
    )
    register_shifu_outline_routes(app, path_prefix)
    register_shifu_mdflow_routes(app, path_prefix)
    register_shifu_outline_tree_routes(app, path_prefix)
    register_shifu_resource_routes(app, path_prefix)
    register_shifu_course_export_routes(app, path_prefix)
    register_shifu_ask_routes(
        app, path_prefix, _admit_creator_debug_usage=_admit_creator_debug_usage
    )
    register_shifu_tts_routes(
        app, path_prefix, _admit_creator_debug_usage=_admit_creator_debug_usage
    )

    return app
