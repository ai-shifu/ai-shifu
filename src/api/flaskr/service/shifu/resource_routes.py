"""Register shifu file upload and video metadata routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error

if TYPE_CHECKING:
    from flask import Flask


def register_shifu_resource_routes(app: Flask, path_prefix: str) -> None:
    """Register file upload, URL upload, and video info routes."""
    from flaskr.service.shifu import route as shifu_route

    @app.route(path_prefix + "/upfile", methods=["POST"])
    def upfile_api() -> str:
        """Upfile to oss.

        ---
        tags:
            - shifu
        parameters:
            - in: formData
              name: file
              type: file
              required: true
              description: documents
        responses:
            200:
                description: upload success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: return msg
                                data:
                                    type: string
                                    description: shifu file url
        """
        file = request.files.get("file", None)
        resource_id = request.values.get("resource_id", None)
        if resource_id is None:
            resource_id = ""
        user_id = request.user.user_id
        if not file:
            raise_param_error("file")
        return make_common_response(
            shifu_route.upload_file(app, user_id, resource_id, file)
        )

    @app.route(path_prefix + "/url-upfile", methods=["POST"])
    def upload_url_api() -> str:
        """Upload url to oss.

        ---
        tags:
            - shifu
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    url:
                        type: string
                        description: url
        responses:
            200:
                description: upload success
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
                                    description: uploaded file url
        """
        user_id = request.user.user_id
        payload = request.get_json(silent=True)
        url = payload.get("url") if isinstance(payload, dict) else None
        if not isinstance(url, str) or not url.strip():
            raise_param_error("url is required")
        return make_common_response(shifu_route.upload_url(app, user_id, url))

    @app.route(path_prefix + "/get-video-info", methods=["POST"])
    def get_video_info_api() -> str:
        """Get video info.

        ---
        tags:
            - shifu
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    url:
                        type: string
                        description: url
        responses:
            200:
                description: get video info success
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
                                    description: video metadata
        """
        user_id = request.user.user_id
        url = request.get_json().get("url")
        if not url:
            raise_param_error("url is required")
        return make_common_response(shifu_route.get_video_info(app, user_id, url))
