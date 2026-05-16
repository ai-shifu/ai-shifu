"""HTTP routes for the creator-analytics DSL query API."""

from __future__ import annotations

from flask import Flask, request

from flaskr.route.common import make_common_response
from flaskr.service.creator_analytics.credit_detail import run as run_credit_detail
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

    @app.route(path_prefix + "/credit-detail", methods=["POST"])
    def creator_analytics_credit_detail():
        """
        Fetch joined credit consumption detail for one shifu.

        Server-side joins ``bill_usage`` and ``credit_ledger_entries`` on
        ``source_bid = usage_bid AND source_type = USAGE``, then returns
        a paginated row list together with a summary block (total records,
        total credits, distinct users / progress records, wallet creator,
        time range). The DSL surface is deliberately untouched —
        ``credit_ledger_entries`` is not in the whitelist; this endpoint is
        the only way creators can read real credit-deduction amounts until
        the daily aggregation cron is enabled and
        ``bill_daily_usage_metrics`` carries data again.
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
                    start_date:
                        type: string
                        description: Optional ISO date (YYYY-MM-DD). Inclusive lower bound.
                    end_date:
                        type: string
                        description: Optional ISO date (YYYY-MM-DD). Inclusive upper bound.
                    usage_scene:
                        type: array
                        items:
                            type: integer
                        description: Optional list, subset of [1201, 1202, 1203].
                    usage_type:
                        type: array
                        items:
                            type: integer
                        description: Optional list, subset of [1101, 1102].
                    limit:
                        type: integer
                    offset:
                        type: integer
        responses:
            200:
                description: Joined credit consumption detail.
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
                                        summary:
                                            type: object
                                        rows:
                                            type: array
                                            items:
                                                type: object
                                        limit:
                                            type: integer
                                        offset:
                                            type: integer
        """

        user_id = request.user.user_id
        payload = request.get_json(silent=True) or {}
        result = run_credit_detail(app, user_id, payload)
        return make_common_response(result)

    return app
