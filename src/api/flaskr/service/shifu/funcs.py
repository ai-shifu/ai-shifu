"""
common shifu funcs

This module contains functions for shifu.

Author: yfge
Date: 2025-08-07
"""

from ...dao import redis_client as redis, db
from .models import FavoriteScenario, AiCourseAuth
from ..common.models import raise_error
from flaskr.service.config import get_config
import uuid
import json
import requests
from io import BytesIO
from urllib.parse import urlparse
import re
from .models import DraftShifu
from ...service.resource.models import Resource
from flaskr.service.common.oss_utils import (
    OSS_PROFILE_COURSES,
    get_image_content_type,
    upload_to_oss,
)


def mark_favorite_shifu(app, user_id: str, shifu_id: str):
    """
    Mark a shifu as favorite for a user.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID to mark as favorite

    Returns:
        bool: True if successful
    """
    with app.app_context():
        existing_favorite_shifu = FavoriteScenario.query.filter_by(
            scenario_id=shifu_id, user_id=user_id
        ).first()
        if existing_favorite_shifu:
            existing_favorite_shifu.status = 1
            db.session.commit()
            return True
        favorite_shifu = FavoriteScenario(
            scenario_id=shifu_id, user_id=user_id, status=1
        )
        db.session.add(favorite_shifu)
        db.session.commit()
        return True


# unmark favorite shifu
def unmark_favorite_shifu(app, user_id: str, shifu_id: str):
    """
    Unmark a shifu as favorite for a user.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID to unmark as favorite

    Returns:
        bool: True if successful
    """
    with app.app_context():
        favorite_shifu = FavoriteScenario.query.filter_by(
            scenario_id=shifu_id, user_id=user_id
        ).first()
        if favorite_shifu:
            favorite_shifu.status = 0
            db.session.commit()
            return True
        return False


def mark_or_unmark_favorite_shifu(app, user_id: str, shifu_id: str, is_favorite: bool):
    """
    Mark or unmark a shifu as favorite for a user.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID to mark or unmark as favorite
        is_favorite: Whether to mark or unmark as favorite

    Returns:
        bool: True if successful
    """
    if is_favorite:
        return mark_favorite_shifu(app, user_id, shifu_id)
    else:
        return unmark_favorite_shifu(app, user_id, shifu_id)


def upload_file(app, user_id: str, resource_id: str, file) -> str:
    """
    Upload a file to OSS.

    Args:
        app: Flask application instance
        user_id: User ID
        resource_id: Resource ID
        file: The file to upload

    Returns:
        str: The URL of the uploaded file
    """
    with app.app_context():
        isUpdate = False
        if resource_id == "":
            file_id = str(uuid.uuid4()).replace("-", "")
        else:
            isUpdate = True
            file_id = resource_id

        content_type = get_image_content_type(file.filename)
        url, BUCKET_NAME = upload_to_oss(
            app,
            file_content=file,
            file_id=file_id,
            content_type=content_type,
            profile=OSS_PROFILE_COURSES,
        )

        if isUpdate:
            resource = Resource.query.filter_by(resource_id=file_id).first()
            resource.name = file.filename
            resource.updated_by = user_id
            db.session.commit()
        else:
            resource = Resource(
                resource_id=file_id,
                name=file.filename,
                type=0,
                oss_bucket=BUCKET_NAME,
                oss_name=file_id,
                url=url,
                status=0,
                is_deleted=0,
                created_by=user_id,
                updated_by=user_id,
            )
            db.session.add(resource)
            db.session.commit()

        return url


def upload_url(app, user_id: str, url: str) -> str:
    """
    Upload a file from a URL to OSS.

    Args:
        app: Flask application instance
        user_id: User ID
        url: The URL of the file to upload

    Returns:
        str: The URL of the uploaded file
    """
    with app.app_context():
        try:
            # Validate URL format
            if not url or not url.strip():
                raise_error("server.file.videoUrlRequired")

            # Ensure URL is properly formatted
            if not url.startswith(("http://", "https://")):
                raise_error("server.file.videoInvalidUrlFormat")

            parsed_url = urlparse(url)
            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": url,
                "Connection": "keep-alive",
            }

            app.logger.info(f"Downloading image from URL: {clean_url}")
            response = requests.get(clean_url, headers=headers, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                app.logger.error(f"Invalid content type: {content_type}")
                raise_error("server.file.fileTypeNotSupport")

            file_content = BytesIO(response.content)

            filename = parsed_url.path.split("/")[-1]
            if "." not in filename:
                ext = content_type.split("/")[-1]
                if ext in ["jpeg", "png", "gif"]:
                    filename = f"{filename}.{ext}"
                else:
                    filename = f"{filename}.jpg"

            content_type = get_image_content_type(filename)
            file_id = str(uuid.uuid4()).replace("-", "")

            url, BUCKET_NAME = upload_to_oss(
                app,
                file_content=file_content,
                file_id=file_id,
                content_type=content_type,
                profile=OSS_PROFILE_COURSES,
            )

            resource = Resource(
                resource_id=file_id,
                name=filename,
                type=0,
                oss_bucket=BUCKET_NAME,
                oss_name=file_id,
                url=url,
                status=0,
                is_deleted=0,
                created_by=user_id,
                updated_by=user_id,
            )
            db.session.add(resource)
            db.session.commit()

            return url

        except requests.RequestException as e:
            app.logger.error(
                f"Failed to download image from URL: {url}, error: {str(e)}"
            )
            raise_error("server.file.fileDownloadFailed")
        except Exception as e:
            app.logger.error(f"Failed to upload image to OSS: {url}, error: {str(e)}")
            raise_error("server.file.fileUploadFailed")


def shifu_permission_verification(
    app,
    user_id: str,
    shifu_id: str,
    auth_type: str,
):
    """
    Verify the permission of a user to a shifu.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        auth_type: The type of permission to verify

    Returns:
        bool: True if the user has the permission
    """
    with app.app_context():
        cache_key = (
            get_config("REDIS_KEY_PREFIX")
            + "shifu_permission:"
            + user_id
            + ":"
            + shifu_id
        )
        cache_key_expire = int(get_config("SHIFU_PERMISSION_CACHE_EXPIRE"))
        cache_result = redis.get(cache_key)
        if cache_result is not None:
            try:
                cached_auth_types = json.loads(cache_result)
                return auth_type in cached_auth_types
            except (json.JSONDecodeError, TypeError):
                redis.delete(cache_key)
        # If it is not in the cache, query the database
        shifu = DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_id,
            DraftShifu.created_user_bid == user_id,
        ).first()
        if shifu:
            # The creator has all the permissions
            # Cache all permissions
            all_auth_types = ["view", "edit", "publish"]
            redis.set(cache_key, json.dumps(all_auth_types), cache_key_expire)
            return True
        else:
            # Collaborators need to verify specific permissions
            auth = AiCourseAuth.query.filter(
                AiCourseAuth.course_id == shifu_id, AiCourseAuth.user_id == user_id
            ).first()
            if auth:
                try:
                    raw_auth_types = json.loads(auth.auth_type)
                    normalized = []
                    if isinstance(raw_auth_types, (list, tuple, set)):
                        normalized = [str(item) for item in raw_auth_types]
                    elif isinstance(raw_auth_types, str):
                        normalized = [raw_auth_types]
                    permissions = set()
                    for item in normalized:
                        lowered = item.lower()
                        if lowered in {"view", "read", "readonly"} or lowered == "1":
                            permissions.add("view")
                        if lowered in {"edit", "write"} or lowered == "2":
                            permissions.update({"view", "edit"})
                        if lowered in {"publish"} or lowered == "4":
                            permissions.add("publish")
                    # Fallback to raw values if mapping failed
                    permissions = permissions or set(normalized)
                    result = auth_type in permissions
                    redis.set(
                        cache_key, json.dumps(list(permissions)), cache_key_expire
                    )
                    return result
                except (json.JSONDecodeError, TypeError):
                    return False
            else:
                return False


def get_video_info(app, user_id: str, url: str) -> dict:
    """
    Obtain video information from a URL.

    Args:
        app: Flask application instance
        user_id: User ID
        url: The URL of the video to get information from

    Returns:
        dict: The video information
    """
    with app.app_context():
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.hostname

            if domain == "bilibili.com" or (
                domain and domain.endswith(".bilibili.com")
            ):
                bv_pattern = r"/video/(BV\w+)"
                match = re.search(bv_pattern, url)
                if not match:
                    raise_error("server.file.videoInvalidBilibiliLink")

                bv_id = match.group(1)
                api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"

                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": "https://www.bilibili.com",
                    "Origin": "https://www.bilibili.com",
                    "Connection": "keep-alive",
                }

                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data["code"] == 0:
                        video_data = data["data"]
                        return {
                            "success": True,
                            "title": video_data["title"],
                            "cover": video_data["pic"],
                            "bvid": bv_id,
                            "author": video_data["owner"]["name"],
                            "duration": video_data["duration"],
                        }
                    else:
                        raise_error("server.file.videoBilibiliApiError")
                else:
                    raise_error("server.file.videoBilibiliApiRequestFailed")
            else:
                raise_error("server.file.videoUnsupportedVideoSite")

        except requests.RequestException as e:
            app.logger.error(f"Failed to fetch video info from {url}: {str(e)}")
            raise_error("server.file.videoNetworkError")
        except KeyError as e:
            app.logger.error(f"Missing expected field in API response: {str(e)}")
            raise_error("server.file.videoParseError")
        except Exception as e:
            app.logger.error(f"Unexpected error getting video info: {str(e)}")
            raise_error("server.file.videoGetInfoError")
