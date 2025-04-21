from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    add_profile_item_quick,
    get_profile_item_definition_option_list,
    save_profile_item,
    delete_profile_item,
)
from flaskr.framework.plugin.inject import inject
from flaskr.service.common import raise_error
from flaskr.service.profile.models import (
    PROFILE_TYPE_VLUES,
)
from flaskr.service.profile.dtos import ProfileValueDto


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
            required: true
            type: string
            description: |
                type,current pass the text or option or all
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

    @app.route(
        f"{path_prefix}/get-profile-item-definition-option-list", methods=["GET"]
    )
    def get_profile_item_definition_option_list_api():
        """
        Get profile item defination option list
        ---
        tags:
          - profiles
        parameters:
          - name: parent_id
            in: query
            required: true
            type: string
        description: |
            Get profile item defination option list
        responses:
          200:
            description: A list of profile item defination option
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
                        $ref: '#/components/schemas/ProfileValueDto'
        """
        parent_id = request.args.get("parent_id")
        return make_common_response(
            get_profile_item_definition_option_list(app, parent_id=parent_id)
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
                body,current pass the profile_id and parent_id and profile_key and profile_type and profile_remark and profile_items
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
                    profile_type,current pass one of the profile_type in ['text', 'option']
                profile_remark:
                  type: string
                  description: |
                    profile_remark,current pass the profile_remark
                profile_items:
                  type: array
                  items:
                    $ref: '#/components/schemas/ProfileValueDto'
                    description: |
                      profile_items, required when profile_type is 'option'
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
            raise_error("PROFILE.PARENT_ID_REQUIRED")
        profile_key = request.get_json().get("profile_key", None)
        if not profile_key:
            raise_error("PROFILE.PROFILE_KEY_REQUIRED")

        profile_type = request.get_json().get("profile_type", None)
        if not profile_type:
            raise_error("PROFILE.PROFILE_TYPE_REQUIRED")
        if profile_type not in PROFILE_TYPE_VLUES.keys():
            raise_error("PROFILE.PROFILE_TYPE_INVALID")
        profile_type = PROFILE_TYPE_VLUES[profile_type]

        profile_remark = request.get_json().get("profile_remark", None)
        profile_items = request.get_json().get("profile_items", None)
        profile_items_list = []
        if profile_items:
            for item in profile_items:
                profile_items_list.append(
                    ProfileValueDto(
                        value=item.get("value", None), name=item.get("name", None)
                    )
                )
        return make_common_response(
            save_profile_item(
                app,
                profile_id=profile_id,
                parent_id=parent_id,
                user_id=user_id,
                key=profile_key,
                type=profile_type,
                remark=profile_remark,
                items=profile_items_list,
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
            raise_error("PROFILE.PROFILE_ID_REQUIRED")
        return make_common_response(delete_profile_item(app, user_id, profile_id))

    @app.route(f"{path_prefix}/get-profile-item", methods=["POST"])
    def get_profile_item_api():
        """
        Get profile item
        """
        pass

    return app
