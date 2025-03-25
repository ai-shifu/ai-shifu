from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.profile.profile_manage import (
    get_profile_item_defination_list,
    add_profile_item_quick,
)
from flaskr.framework.plugin.inject import inject


@inject
def register_profile_routes(app: Flask, path_prefix: str = "/api/profiles"):
    @app.route(f"{path_prefix}/get-profile-item-definations", methods=["GET"])
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
                        $ref: '#/components/schemas/ProfileItemDefination'
        """
        parent_id = request.args.get("parent_id")
        return make_common_response(
            get_profile_item_defination_list(app, parent_id=parent_id)
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
                                  $ref: '#/components/schemas/ProfileItemDefination'
        """
        parent_id = request.get_json().get("parent_id", None)
        profile_key = request.get_json().get("profile_key", None)
        user_id = request.user.user_id
        return make_common_response(
            add_profile_item_quick(app, parent_id, profile_key, user_id)
        )

    return app
