"""HTTP routes for the creator-analytics DSL query API."""

from __future__ import annotations

from flask import Flask, request

from flaskr.route.common import make_common_response
from flaskr.service.creator_analytics.funcs import run_dsl


def register_creator_analytics_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/query", methods=["POST"])
    def creator_analytics_query():
        """
        Run a creator-analytics DSL query.
        ---
        tags:
            - creator-analytics
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    shifu_bid:
                        type: string
                        description: Course id the caller must have view permission on.
                    table:
                        type: string
                        description: Whitelisted table key.
                    select:
                        type: array
                        items:
                            type: string
                    where:
                        type: array
                        items:
                            type: object
                    group_by:
                        type: array
                        items:
                            type: string
                    aggregate:
                        type: array
                        items:
                            type: object
                    order_by:
                        type: array
                        items:
                            type: object
                    limit:
                        type: integer
                    offset:
                        type: integer
        responses:
            200:
                description: Aggregated query result.
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    type: object
                                    properties:
                                        columns:
                                            type: array
                                            items:
                                                type: string
                                        rows:
                                            type: array
                                            items:
                                                type: array
                                        limit:
                                            type: integer
                                        offset:
                                            type: integer
        """

        user_id = request.user.user_id
        payload = request.get_json(silent=True) or {}
        result = run_dsl(app, user_id, payload)
        return make_common_response(result)

    return app
