"""Expose HTTP routes for learner profiles."""

from flask import Flask, request
from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.common import raise_error
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    get_profile_variable_usage,
    hide_unused_profile_items,
    update_profile_item_hidden_state,
)


@inject
def register_profile_routes(app: Flask, path_prefix: str = "/api/profiles") -> Flask:
    """Register learner-profile routes on the Flask application."""

    @app.route(f"{path_prefix}/get-profile-item-definitions", methods=["GET"])
    def get_profile_item_defination_api() -> str:
        """Get profile item defination.

        ---
        tags:
          - profiles
        parameters:
          - name: parent_id
            in: query
            required: true
            type: string
            description: |
                parent_id,current pass the scenario_id
        description: |
            Get profile item defination
        responses:
          200:
            description: A list of profile item defination
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    code:
                      type: integer
                    message:
                      type: string
                    data:
                      type: array
                      items:
                        $ref: '#/components/schemas/ProfileItemDefinition'
        """
        parent_id = request.args.get("parent_id")
        return make_common_response(
            get_profile_item_definition_list(app, parent_id=parent_id)
        )

    @app.route(f"{path_prefix}/hide-unused-profile-items", methods=["POST"])
    def hide_unused_profile_items_api() -> str:
        """Hide all unused custom profile items under a shifu.

        ---
        tags:
          - profiles
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  parent_id:
                    type: string
                    description: shifu_bid
        responses:
          200:
            description: OK
        """
        payload = request.get_json(silent=True) or {}
        parent_id = payload.get("parent_id")
        if not parent_id:
            raise_error("server.profile.parentIdRequired")
        user_id = request.user.user_id
        return make_common_response(
            hide_unused_profile_items(app, parent_id=parent_id, user_id=user_id)
        )

    @app.route(f"{path_prefix}/profile-variable-usage", methods=["GET"])
    def get_profile_variable_usage_api() -> str:
        """Get variable usage across all outlines for a shifu.

        ---
        tags:
          - profiles
        parameters:
          - name: parent_id
            in: query
            required: true
            type: string
            description: shifu_bid
        responses:
          200:
            description: OK
        """
        parent_id = request.args.get("parent_id")
        if not parent_id:
            raise_error("server.profile.parentIdRequired")
        return make_common_response(
            get_profile_variable_usage(app, parent_id=parent_id)
        )

    @app.route(f"{path_prefix}/update-profile-hidden-state", methods=["POST"])
    def update_profile_hidden_state_api() -> str:
        """Hide or restore specific custom profile items.

        ---
        tags:
          - profiles
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  parent_id:
                    type: string
                    description: shifu_bid
                  profile_keys:
                    type: array
                    items:
                      type: string
                  hidden:
                    type: boolean
        responses:
          200:
            description: OK
        """
        payload = request.get_json(silent=True) or {}
        parent_id = payload.get("parent_id")
        profile_keys = payload.get("profile_keys", []) or []
        hidden = bool(payload.get("hidden", True))
        if not parent_id:
            raise_error("server.profile.parentIdRequired")
        user_id = request.user.user_id
        return make_common_response(
            update_profile_item_hidden_state(
                app,
                parent_id=parent_id,
                profile_keys=profile_keys,
                hidden=hidden,
                user_id=user_id,
            )
        )

    return app
