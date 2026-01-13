"""
MDF Conversion Service Routes

Provides proxy endpoints for MDF (Markdown Flow) conversion
to abstract external API calls from frontend.
"""

from flask import Flask, request, current_app
from flaskr.route.common import make_common_response
from flaskr.framework.plugin.inject import inject
from flaskr.service.common.models import raise_param_error
from .funcs import convert_text_to_mdf


@inject
def register_gen_mdf_routes(app: Flask, path_prefix="/api/gen_mdf"):
    """Register MDF conversion routes"""
    app.logger.info(f"register gen_mdf routes {path_prefix}")

    @app.route(path_prefix + "/convert", methods=["POST"], endpoint="gen_mdf_convert")
    def gen_mdf_convert_api():
        """
        Convert text to MDF format via external API
        ---
        tags:
            - gen_mdf
            - cook
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                required:
                  - text
                  - language
                properties:
                  text:
                    type: string
                    description: Text content to convert
                    example: "This is a sample text"
                  language:
                    type: string
                    description: Target language (e.g., Chinese, English)
                    example: "English"
                  output_mode:
                    type: string
                    description: Output mode
                    default: "content"
                    example: "content"
        responses:
            200:
                description: Successful conversion
                schema:
                  type: object
                  properties:
                    content_prompt:
                      type: string
                      description: Converted MDF content
                    request_id:
                      type: string
                      description: Request identifier
                    timestamp:
                      type: string
                      description: Conversion timestamp
                    metadata:
                      type: object
                      properties:
                        input_length:
                          type: integer
                        output_length:
                          type: integer
                        language:
                          type: string
                        user_id:
                          type: string
            400:
                description: Invalid request parameters
            503:
                description: MDF API not configured or unavailable
        """
        data = request.get_json()

        # Validate required parameters
        text = data.get("text", "").strip()
        if not text:
            raise_param_error("TEXT_REQUIRED")

        if len(text) > 10000:
            raise_param_error("TEXT_TOO_LONG")

        language = data.get("language", "English")
        output_mode = data.get("output_mode", "content")

        # Call business logic
        result = convert_text_to_mdf(
            app=current_app, text=text, language=language, output_mode=output_mode
        )

        return make_common_response(result)

    @app.route(
        path_prefix + "/config-status",
        methods=["GET"],
        endpoint="gen_mdf_config_status",
    )
    def get_gen_mdf_config_status():
        """
        Check if MDF API is configured
        ---
        tags:
            - gen_mdf
            - config
        responses:
            200:
                description: Configuration status
                schema:
                  type: object
                  properties:
                    configured:
                      type: boolean
                      description: Whether MDF API URL is configured
        """
        from flaskr.common.config import get_config

        mdf_api_url = get_config("GEN_MDF_API_URL")
        mdf_app_id = get_config("GEN_MDF_APP_ID")

        url_configured = bool(mdf_api_url and mdf_api_url.strip())
        app_id_configured = bool(mdf_app_id and mdf_app_id.strip())

        return make_common_response(
            {"configured": url_configured and app_id_configured}
        )

    return app
