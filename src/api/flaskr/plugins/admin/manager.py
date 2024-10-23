from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.plugins.view.funs import export_query, query_view, get_view


def register_data_manager_route(app: Flask, path_prefix):
    @app.route(path_prefix + "/view-info", methods=["POST"])
    def get_view_route():
        user_id = request.user.user_id
        view_name = request.json.get("view_name")
        return make_common_response(get_view(app, user_id, view_name))

    @app.route(path_prefix + "/query-view", methods=["POST"])
    def query_view_route():
        user_id = request.user.user_id
        view_name = request.get_json().get("view_name")
        if view_name is None:
            raise_param_error("view_name")
        page = request.get_json().get("page", 1)
        page_size = request.get_json().get("page_size", 20)
        query = request.get_json().get("query", {})
        sort = request.get_json().get("sort", [])
        return make_common_response(
            query_view(app, user_id, view_name, page, page_size, query, sort)
        )

    @app.route(path_prefix + "/export-query", methods=["POST"])
    def export_query_route():
        user_id = request.user.user_id
        view_name = request.get_json().get("view_name")
        if view_name is None:
            raise_param_error("view_name")
        query = request.get_json().get("query", {})
        return export_query(app, user_id, view_name, query)

    return app
