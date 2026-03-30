from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    add_profile_item_quick,
    save_profile_item,
    delete_profile_item,
    update_profile_item_hidden_state,
    hide_unused_profile_items,
    get_profile_variable_usage,
)
from flaskr.framework.plugin.inject import inject
from flaskr.service.common import raise_error


@inject
def register_profile_routes(app: Flask, path_prefix: str = "/api/profiles"):
    @app.route(f"{path_prefix}/get-profile-item-definitions", methods=["GET"])
    def get_profile_item_defination_api():
        """
        Get profile item defination
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
          - name: type
            in: query
            required: false
            type: string
            description: |
                type,current pass text or all; both return the same variable list
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
        type = request.args.get("type", "all")
        return make_common_response(
            get_profile_item_definition_list(app, parent_id=parent_id, type=type)
        )

    @app.route(f"{path_prefix}/hide-unused-profile-items", methods=["POST"])
    def hide_unused_profile_items_api():
        """
        Hide all unused custom profile items under a shifu.
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
    def get_profile_variable_usage_api():
        """
        Get variable usage across all outlines for a shifu.
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
    def update_profile_hidden_state_api():
        """
        Hide or restore specific custom profile items.
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

    @app.route(f"{path_prefix}/add-profile-item-quick", methods=["POST"])
    def add_profile_item_quick_api():
        """
        Add profile item
        ---
        tags:
          - profiles
        parameters:
          - name: parent_id
            in: body
            required: true
            type: string
            description: |
                parent_id,current pass the scenario_id
          - name: profile_key
            in: body
            required: true
            type: string
            description: |
                profile_key , which is the key of the profile item and could be used in prompt
        description: |
            Add profile item
        responses:
            200:
                description: Add profile item success
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
                                  $ref: '#/components/schemas/ProfileItemDefinition'
        """
        parent_id = request.get_json().get("parent_id", None)
        profile_key = request.get_json().get("profile_key", None)
        user_id = request.user.user_id
        return make_common_response(
            add_profile_item_quick(app, parent_id, profile_key, user_id)
        )

    @app.route(f"{path_prefix}/save-profile-item", methods=["POST"])
    def save_profile_item_api():
        """
        save profile item
        ---
        tags:
          - profiles
        parameters:
          - name: body
            in: body
            required: true
            description: |
                body,current pass the profile_id and parent_id and profile_key
            schema:
              type: object
              properties:
                profile_id:
                  type: string
                  required: false
                  description: |
                    profile_id,current pass the profile_id
                    if not pass,it will be a new profile item
                parent_id:
                  type: string
                  required: true
                  description: |
                    parent_id,current pass the scenario_id
                profile_key:
                  type: string
                  required: true
                  description: |
                    profile_key,current pass the profile_key
                profile_type:
                  type: string
                  required: true
                  description: |
                    profile_type,current pass 'text'
        description: |
            Save profile item
        responses:
          200:
            description: Save profile item success
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/ProfileItemDefinition'
        """
        user_id = request.user.user_id
        profile_id = request.get_json().get("profile_id", None)
        parent_id = request.get_json().get("parent_id", None)
        if not parent_id:
            raise_error("server.profile.parentIdRequired")
        profile_key = request.get_json().get("profile_key", None)
        if not profile_key:
            raise_error("server.profile.profileKeyRequired")

        profile_type = request.get_json().get("profile_type", None)
        if not profile_type:
            raise_error("server.profile.profileTypeRequired")
        if profile_type != "text":
            raise_error("server.profile.profileTypeInvalid")
        return make_common_response(
            save_profile_item(
                app,
                profile_id=profile_id,
                parent_id=parent_id,
                user_id=user_id,
                key=profile_key,
            )
        )

    @app.route(f"{path_prefix}/delete-profile-item", methods=["POST"])
    def delete_profile_item_api():
        """
        Delete profile item
        ---
        tags:
          - profiles
        parameters:
          - name: body
            in: body
            required: true
            type: object
            schema:
              type: object
              properties:
                profile_id:
                  type: string
                  required: true
                  description: |
                      profile_id,current pass the profile_id
        description: |
            Delete profile item
        responses:
            200:
                description: Delete profile item success
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
                                  $ref: '#/components/schemas/ProfileItemDefinition'
        """
        user_id = request.user.user_id
        profile_id = request.get_json().get("profile_id", None)
        if not profile_id:
            raise_error("server.profile.profileIdRequired")
        return make_common_response(delete_profile_item(app, user_id, profile_id))

    @app.route(f"{path_prefix}/get-profile-item", methods=["POST"])
    def get_profile_item_api():
        """
        Get profile item
        """
        pass

    return app
