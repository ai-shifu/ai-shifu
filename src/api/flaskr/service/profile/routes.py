from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.profile.profile_manage import (
    get_profile_item_defination_list,
    add_profile_item_quick,
)


def register_profile_routes(app: Flask, path_prefix: str = "profiles"):
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
        responses:
          200:
            description: A list of profile item defination
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
                    $ref: '#/definitions/ProfileItemDefination'
        """
        parent_id = request.args.get("parent_id")
        return make_common_response(
            get_profile_item_defination_list(app, parent_id=parent_id)
        )

    @app.route(f"{path_prefix}/add-profile-item", methods=["POST"])
    def add_profile_item_api():
        """
        Add profile item
        ---
        tags:
          - profiles
        parameters:
          - name: parent_id
            in: query
            required: true
            type: string

          - name: key
            in: query
            required: true
            type: string
        responses:
            schema:
              type: object
              properties:
                code:
                  type: integer
                message:
                  type: string
                data:
                  type: object
                  $ref: '#/definitions/ProfileItemDefination'
        """
        parent_id = request.args.get("parent_id")
        key = request.args.get("key")
        user_id = request.user.user_id
        return make_common_response(
            add_profile_item_quick(app, parent_id, key, user_id)
        )

    return app
