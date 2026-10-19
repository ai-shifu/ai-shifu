"""Register shifu sharing-permission routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.shifu.models import AiCourseAuth

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def register_shifu_permission_routes(
    app: Flask, path_prefix: str, *, _require_shifu_owner: Callable[[str], str]
) -> None:
    """Register course permission list, grant, and remove routes."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_bid>/permissions", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def list_shifu_permissions_api(shifu_bid: str) -> str:
        """List shared permissions for a shifu."""
        owner_id = _require_shifu_owner(shifu_bid)
        contact_type = shifu_route._normalize_contact_type(
            request.args.get("contact_type", "")
        )
        allowed_methods = shifu_route._get_login_methods_enabled()
        if contact_type and contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if contact_type and allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")
        if not contact_type:
            contact_type = "email" if "email" in allowed_methods else "phone"

        items = []
        auths = AiCourseAuth.query.filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.status == 1,
        ).all()
        for auth in auths:
            if not auth.user_id or auth.user_id == owner_id:
                continue
            aggregate = shifu_route.load_user_aggregate(auth.user_id)
            if not aggregate:
                continue
            auth_types = shifu_route._normalize_auth_types(auth.auth_type)
            permissions = (
                shifu_route._auth_types_to_permissions(auth_types) or auth_types
            )
            if "publish" in permissions:
                permission = "publish"
            elif "edit" in permissions:
                permission = "edit"
            elif "view" in permissions:
                permission = "view"
            else:
                continue

            if contact_type == "email":
                identifier = aggregate.email or ""
            elif contact_type == "phone":
                identifier = aggregate.mobile or ""
            else:
                identifier = aggregate.email or aggregate.mobile or ""
            if not identifier:
                continue

            items.append(
                {
                    "user_id": aggregate.user_bid,
                    "identifier": identifier or "",
                    "nickname": aggregate.nickname or "",
                    "permission": permission,
                }
            )
        return make_common_response({"items": items})

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/permissions/grant",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def grant_shifu_permissions_api(shifu_bid: str) -> str:
        """Grant shared permissions for a shifu."""
        owner_id = _require_shifu_owner(shifu_bid)
        payload = request.get_json() or {}
        contact_type = shifu_route._normalize_contact_type(
            payload.get("contact_type", "")
        )
        raw_contacts = payload.get("contacts", [])
        permission = shifu_route._normalize_contact_type(payload.get("permission", ""))

        allowed_methods = shifu_route._get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")
        if permission not in {"view", "edit", "publish"}:
            raise_param_error("permission")

        contacts = shifu_route._normalize_contacts(raw_contacts)
        if not contacts:
            raise_param_error("contact")

        contacts = shifu_route._validate_contacts(contact_type, contacts)
        if not contacts:
            raise_param_error("contact")

        count = shifu_route.grant_shifu_permissions(
            app,
            shifu_bid=shifu_bid,
            owner_id=owner_id,
            contact_type=contact_type,
            contacts=contacts,
            permission=permission,
        )
        return make_common_response({"count": count})

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/permissions/remove",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def remove_shifu_permissions_api(shifu_bid: str) -> str:
        """Remove a shared permission from a shifu."""
        owner_id = _require_shifu_owner(shifu_bid)
        payload = request.get_json() or {}
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            raise_param_error("user_id")
        if user_id == owner_id:
            raise_error("server.shifu.noPermission")

        shifu_route.remove_shifu_permission(app, shifu_bid=shifu_bid, user_id=user_id)
        return make_common_response({"removed": True})
