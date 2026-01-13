"""
MDF Conversion Business Logic

Handles communication with external MDF API service.
"""

import requests
import logging
from typing import Dict, Any
from flaskr.service.config import get_config
from flaskr.service.common.models import raise_error_with_args

logger = logging.getLogger(__name__)

# Configuration constants
MDF_API_TIMEOUT = 60  # 60 seconds timeout for MDF API calls


def convert_text_to_mdf(
    text: str, language: str, output_mode: str = "content"
) -> Dict[str, Any]:
    """
    Convert text to MDF format using external API

    Args:
        app: Flask application instance
        text: Text content to convert
        language: Target language (Chinese/English)
        output_mode: Output mode (default: "content")

    Returns:
        Dict containing conversion result with keys:
            - content_prompt: Converted MDF content
            - request_id: Request identifier
            - timestamp: Conversion timestamp
            - metadata: Additional metadata

    Raises:
        Exception: If MDF API is not configured or request fails
    """
    # Get MDF API configuration
    mdf_api_url = get_config("GEN_MDF_API_URL")
    mdf_app_id = get_config("GEN_MDF_APP_ID")

    if not mdf_api_url:
        app.logger.error("MDF API URL not configured")
        raise_error_with_args("MDF_API_NOT_CONFIGURED")

    if not mdf_app_id:
        app.logger.error("MDF API App ID not configured")
        raise_error_with_args("MDF_API_NOT_CONFIGURED")

    # Construct API endpoint (v1 API with X-App-Id authentication)
    api_endpoint = f"{mdf_api_url.rstrip('/')}/gen/v1/text2mdf"

    # Prepare request payload
    payload = {"text": text, "language": language, "output_mode": output_mode}

    try:
        app.logger.info(
            f"Calling MDF API at {api_endpoint} for text length {len(text)}"
        )

        # Make HTTP request to external MDF API
        response = requests.post(
            api_endpoint,
            json=payload,
            timeout=MDF_API_TIMEOUT,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AI-Shifu/1.0",
                "X-App-Id": mdf_app_id,
            },
        )

        # Check response status
        if response.status_code == 401:
            app.logger.error(f"MDF API authentication failed: {response.text[:500]}")
            raise_error_with_args("MDF_API_UNAUTHORIZED")
        elif response.status_code == 422:
            app.logger.error(
                f"MDF API validation error (missing X-App-Id?): {response.text[:500]}"
            )
            raise_error_with_args("MDF_API_ERROR")
        elif response.status_code != 200:
            app.logger.error(
                f"MDF API returned non-200 status: {response.status_code}, "
                f"body: {response.text[:500]}"
            )
            raise_error_with_args("MDF_API_ERROR")

        # Parse response
        result = response.json()

        app.logger.info(
            f"MDF conversion successful, output length: "
            f"{result.get('metadata', {}).get('output_length', 'unknown')}"
        )

        return result

    except requests.exceptions.Timeout:
        app.logger.error(f"MDF API request timeout after {MDF_API_TIMEOUT}s")
        raise_error_with_args("MDF_API_TIMEOUT")

    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"MDF API connection error: {str(e)}")
        raise_error_with_args("MDF_API_CONNECTION_ERROR")

    except requests.exceptions.RequestException as e:
        app.logger.error(f"MDF API request failed: {str(e)}")
        raise_error_with_args("MDF_API_REQUEST_ERROR")

    except ValueError as e:
        app.logger.error(f"Failed to parse MDF API response: {str(e)}")
        raise_error_with_args("MDF_API_INVALID_RESPONSE")
