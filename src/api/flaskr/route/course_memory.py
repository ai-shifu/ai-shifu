"""Authenticated, self-service access to custom current-course memory."""

from flask import Flask, request

from flaskr.common.http import sensitive_body
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.profile.api import (
    delete_course_memory,
    list_course_memory,
)


def _identifier(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or not value.isascii()
        or not value.isalnum()
    ):
        raise_param_error(name)
    return value


def _version(value: object, name: str) -> int:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdecimal()
        or len(value) > 19
        or not 0 < int(value) < 2**63
    ):
        raise_param_error(name)
    return int(value)


def register_course_memory_routes(app: Flask, path_prefix: str) -> None:
    """Use the user route's authentication hook; never accept an owner from clients."""

    @app.route(path_prefix + "/course-memory", methods=["GET"])
    @sensitive_body()
    def course_memory_list_api() -> str:
        course = _identifier(request.args.get("course_id"), "course_id")
        raw = request.args.get("before")
        before = _version(raw, "before") if raw is not None else None
        return make_common_response(
            list_course_memory(request.user.user_id, course, before=before)
        )

    @app.route(path_prefix + "/course-memory", methods=["POST"])
    @sensitive_body()
    def course_memory_delete_api() -> str:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {"course_id", "value_id"}:
            raise_param_error("course_memory")
        course = _identifier(payload["course_id"], "course_id")
        value_id = _version(payload["value_id"], "value_id")
        return make_common_response(
            delete_course_memory(request.user.user_id, course, value_id)
        )
