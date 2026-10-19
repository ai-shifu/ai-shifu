"""Register shifu MarkdownFlow content and history routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flask import Response, request
from flaskr.common.http import fmt, make_common_response
from flaskr.common.shifu_context import with_shifu_context
from flaskr.i18n import _
from flaskr.service.common.models import ERROR_CODE, raise_param_error

if TYPE_CHECKING:
    from flask import Flask


def register_shifu_mdflow_routes(app: Flask, path_prefix: str) -> None:
    """Register MarkdownFlow read, save, parse, history, and run routes."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow",
        methods=["GET"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_mdflow_api(shifu_bid: str, outline_bid: str) -> str:
        """Get mdflow.

        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: get mdflow success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: string
                                    description: mdflow
        """
        return make_common_response(
            shifu_route.get_shifu_mdflow(app, shifu_bid, outline_bid)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/draft-meta",
        methods=["GET"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_draft_meta_api(shifu_bid: str) -> str:
        """Get draft meta.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              in: query
              type: string
              required: false
        responses:
            200:
                description: get draft meta success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    properties:
                                        revision:
                                            type: integer
                                            description: latest draft revision (course-level or outline content-level when outline_bid is provided)
                                        updated_at:
                                            type: string
                                            description: last update timestamp as UTC ISO 8601 with Z suffix
                                        updated_user:
                                            type: object
                                            properties:
                                                user_bid:
                                                    type: string
                                                    description: updater user bid
                                                phone:
                                                    type: string
                                                    description: masked phone or email
        """
        outline_bid = request.args.get("outline_bid")
        return make_common_response(
            shifu_route.get_shifu_draft_meta(app, shifu_bid, outline_bid)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def save_mdflow_api(shifu_bid: str, outline_bid: str) -> str | Response:
        """Save mdflow.

        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - name: shifu_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    data:
                        type: string
                        description: mdflow
                    base_revision:
                        type: integer
                        description: current outline content draft revision
        responses:
            200:
                description: save mdflow success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    properties:
                                        new_revision:
                                            type: integer
                                            description: latest outline content draft revision
        """
        user_id = request.user.user_id
        json_data = request.get_json(silent=True) or {}
        if not isinstance(json_data, dict):
            raise_param_error("json body")
        content = json_data.get("data") or ""
        base_revision = json_data.get("base_revision")
        if base_revision is not None:
            try:
                base_revision = int(base_revision)
            except (TypeError, ValueError):
                raise_param_error("base_revision")
        result = shifu_route.save_shifu_mdflow(
            app, user_id, shifu_bid, outline_bid, content, base_revision
        )
        if result.get("conflict"):
            body = json.dumps(
                {
                    "code": ERROR_CODE["server.shifu.draftConflict"],
                    "message": _("server.shifu.draftConflict"),
                    "data": {"meta": result.get("meta")},
                },
                default=fmt,
                ensure_ascii=False,
            )
            return Response(body, status=200, mimetype="application/json")
        return make_common_response({"new_revision": result.get("new_revision")})

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/parse",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def parse_mdflow_api(shifu_bid: str, outline_bid: str) -> str:
        """Parse mdflow.

        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    data:
                        type: string
                        description: mdflow
        responses:
            200:
                description: parse mdflow success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    $ref: "#/components/schemas/MdflowDTOParseResult"
        """
        data = request.get_json().get("data", None)
        return make_common_response(
            shifu_route.parse_shifu_mdflow(app, shifu_bid, outline_bid, data)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/history",
        methods=["GET"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_mdflow_history_api(shifu_bid: str, outline_bid: str) -> str:
        """Get mdflow history.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
            - name: limit
              in: query
              type: integer
              required: false
              description: max number of history items, default 100, range 1-200
            - name: timezone
              in: query
              type: string
              required: false
              description: IANA timezone, e.g. Asia/Shanghai
        responses:
            200:
                description: get mdflow history success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    properties:
                                        items:
                                            type: array
                                            items:
                                                type: object
                                                properties:
                                                    version_id:
                                                        type: integer
                                                        description: outline history version id
                                                    updated_at:
                                                        type: string
                                                        description: UTC update timestamp (ISO 8601)
                                                    updated_user_bid:
                                                        type: string
                                                        description: updater user bid
                                                    updated_user_name:
                                                        type: string
                                                        description: updater display name
        """
        limit_raw = request.args.get("limit", 100)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            raise_param_error("limit")
        if limit < 1 or limit > 200:
            raise_param_error("limit")
        return make_common_response(
            shifu_route.get_shifu_mdflow_history(app, shifu_bid, outline_bid, limit)
        )

    @app.route(
        path_prefix
        + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/history/<version_id>",
        methods=["GET"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_mdflow_history_version_detail_api(
        shifu_bid: str, outline_bid: str, version_id: str
    ) -> str:
        """Get mdflow history version detail.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
            - name: version_id
              type: integer
              required: true
            - name: timezone
              in: query
              type: string
              required: false
              description: IANA timezone, e.g. Asia/Shanghai
        responses:
            200:
                description: get mdflow history version detail success
        """
        try:
            version_id_int = int(version_id)
        except (TypeError, ValueError):
            raise_param_error("version_id")
        if version_id_int <= 0:
            raise_param_error("version_id")

        return make_common_response(
            shifu_route.get_shifu_mdflow_history_version_detail(
                app,
                shifu_bid,
                outline_bid,
                version_id_int,
            )
        )

    @app.route(
        path_prefix
        + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/history/restore",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def restore_mdflow_history_api(shifu_bid: str, outline_bid: str) -> str | Response:
        """Restore mdflow history version.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    version_id:
                        type: integer
                        description: target history version id
                    base_revision:
                        type: integer
                        description: current draft revision from client
        responses:
            200:
                description: restore mdflow history success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    properties:
                                        restored:
                                            type: boolean
                                            description: whether restore changed current content
                                        new_revision:
                                            type: integer
                                            description: latest draft revision
                                        lesson_deleted:
                                            type: boolean
                                            description: whether the outline has already been deleted
        """
        user_id = request.user.user_id
        json_data = request.get_json() or {}
        version_id = json_data.get("version_id")
        base_revision = json_data.get("base_revision")
        try:
            version_id = int(version_id)
        except (TypeError, ValueError):
            raise_param_error("version_id")
        if version_id <= 0:
            raise_param_error("version_id")
        if base_revision is not None:
            try:
                base_revision = int(base_revision)
            except (TypeError, ValueError):
                raise_param_error("base_revision")
        result = shifu_route.restore_shifu_mdflow_history_version(
            app, user_id, shifu_bid, outline_bid, version_id, base_revision
        )
        if result.get("conflict"):
            body = json.dumps(
                {
                    "code": ERROR_CODE["server.shifu.draftConflict"],
                    "message": _("server.shifu.draftConflict"),
                    "data": {"meta": result.get("meta")},
                },
                default=fmt,
                ensure_ascii=False,
            )
            return Response(body, status=200, mimetype="application/json")
        return make_common_response(result)

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/run",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def run_mdflow_api(shifu_bid: str, outline_bid: str) -> None:
        """Run mdflow.

        Raises:
            NotImplementedError: This API endpoint is not yet implemented

        """
        message = "MDFlow run API is not yet implemented"
        raise NotImplementedError(message)
