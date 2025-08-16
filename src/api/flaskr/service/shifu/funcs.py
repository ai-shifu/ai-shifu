"""
common shifu funcs

This module contains functions for shifu.

Author: yfge
Date: 2025-08-07
"""

from ...dao import redis_client as redis, db
from .models import FavoriteScenario, AiCourseAuth
from ..common.models import raise_error, raise_error_with_args
from ...common.config import get_config
import oss2
import uuid
import json
import requests
from io import BytesIO
from urllib.parse import urlparse
import re
import time
from .models import DraftShifu
from ...service.resource.models import Resource
from aliyunsdkcore.client import AcsClient
from aliyunsdkcdn.request.v20180510.PushObjectCacheRequest import (
    PushObjectCacheRequest,
)
from aliyunsdkcdn.request.v20180510.DescribeRefreshTasksRequest import (
    DescribeRefreshTasksRequest,
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


def get_content_type(filename):
    """
    Get the content type of a file.

    Args:
        filename: The filename to get the content type of
    Returns:
        The content type of the file
    """

    extension = filename.rsplit(".", 1)[1].lower()
    if extension in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif extension == "png":
        return "image/png"
    elif extension == "gif":
        return "image/gif"
    raise_error("FILE.FILE_TYPE_NOT_SUPPORT")


def _warm_up_cdn(app, url: str, ALI_API_ID: str, ALI_API_SECRET: str, endpoint: str):
    """
    Warm up a CDN URL.

    Args:
        app: Flask application instance
        url: The URL to warm up
        ALI_API_ID: The Alibaba Cloud API ID
        ALI_API_SECRET: The Alibaba Cloud API Secret
        endpoint: The Alibaba Cloud endpoint

    Returns:
        bool: True if successful
    """
    try:

        file_id = url.split("/")[-1]

        region_id = endpoint.split(".")[0].replace("oss-", "")
        client = AcsClient(ALI_API_ID, ALI_API_SECRET, region_id=region_id)
        request = PushObjectCacheRequest()
        request.set_accept_format("json")
        object_path = url.strip() + "\n"
        request.set_ObjectPath(object_path)

        response = client.do_action_with_exception(request)
        response_data = json.loads(response)
        push_task_id = response_data.get("PushTaskId")

        max_retries = 10
        retry_count = 0
        while retry_count < max_retries:
            status_request = DescribeRefreshTasksRequest()
            status_request.set_accept_format("json")
            status_request.TaskId = push_task_id

            status_response = client.do_action_with_exception(status_request)
            status_data = json.loads(status_response)

            tasks = status_data.get("Tasks", {}).get("CDNTask", [])
            if tasks:
                task = tasks[0]
                status = task.get("Status")
                if status == "Complete":
                    max_url_retries = 10
                    url_retry_count = 0
                    while url_retry_count < max_url_retries:
                        try:
                            response = requests.head(url, timeout=5)
                            if response.status_code == 200:
                                return True
                            else:
                                app.logger.warning(
                                    f"The image URL is inaccessible. Status code: {response.status_code}"
                                )
                        except Exception as e:
                            app.logger.warning(
                                f"The image URL access check failed: {str(e)}"
                            )

                        url_retry_count += 1
                        if url_retry_count < max_url_retries:
                            time.sleep(2)

                    app.logger.warning(
                        "The image URL still cannot be accessed after multiple retries"
                    )
                    return False
                elif status == "Failed":
                    app.logger.warning(
                        f"The CDN preheating task failed: {task.get('Description')}"
                    )
                    return False

            retry_count += 1
            if retry_count < max_retries:
                time.sleep(1)

        return False

    except Exception as e:
        app.logger.warning(f"CDN preheating failed: {str(e)}")
        app.logger.warning(f"Preheating URL: {url}")
        app.logger.warning(
            f"ObjectPath: {object_path if 'object_path' in locals() else 'Not set'}"
        )
        return False


def _upload_to_oss(app, file_content, file_id: str, content_type: str) -> str:
    """
    Upload a file to OSS.

    Args:
        app: Flask application instance
        file_content: The content of the file
        file_id: The ID of the file
        content_type: The content type of the file

    Returns:
        str: The URL of the uploaded file
    """
    endpoint = get_config("ALIBABA_CLOUD_OSS_COURSES_ENDPOINT")
    ALI_API_ID = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID")
    ALI_API_SECRET = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET")
    FILE_BASE_URL = get_config("ALIBABA_CLOUD_OSS_COURSES_URL")
    BUCKET_NAME = get_config("ALIBABA_CLOUD_OSS_COURSES_BUCKET")

    if not ALI_API_ID or not ALI_API_SECRET:
        app.logger.warning(
            "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID or ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET not configured"
        )
        raise_error_with_args(
            "API.ALIBABA_CLOUD_NOT_CONFIGURED",
            config_var="ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID,ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET",
        )

    auth = oss2.Auth(ALI_API_ID, ALI_API_SECRET)
    bucket = oss2.Bucket(auth, endpoint, BUCKET_NAME)

    bucket.put_object(
        file_id,
        file_content,
        headers={"Content-Type": content_type},
    )

    url = FILE_BASE_URL + "/" + file_id

    _warm_up_cdn(app, url, ALI_API_ID, ALI_API_SECRET, endpoint)

    return url, BUCKET_NAME


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

        content_type = get_content_type(file.filename)
        url, BUCKET_NAME = _upload_to_oss(app, file, file_id, content_type)

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
                oss_name=BUCKET_NAME,
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
                raise_error("FILE.VIDEO_URL_REQUIRED")

            # Ensure URL is properly formatted
            if not url.startswith(("http://", "https://")):
                raise_error("FILE.VIDEO_INVALID_URL_FORMAT")

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
                raise_error("FILE.FILE_TYPE_NOT_SUPPORT")

            file_content = BytesIO(response.content)

            filename = parsed_url.path.split("/")[-1]
            if "." not in filename:
                ext = content_type.split("/")[-1]
                if ext in ["jpeg", "png", "gif"]:
                    filename = f"{filename}.{ext}"
                else:
                    filename = f"{filename}.jpg"

            content_type = get_content_type(filename)
            file_id = str(uuid.uuid4()).replace("-", "")

            url, BUCKET_NAME = _upload_to_oss(app, file_content, file_id, content_type)

            resource = Resource(
                resource_id=file_id,
                name=filename,
                type=0,
                oss_bucket=BUCKET_NAME,
                oss_name=BUCKET_NAME,
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
            raise_error("FILE.FILE_DOWNLOAD_FAILED")
        except Exception as e:
            app.logger.error(f"Failed to upload image to OSS: {url}, error: {str(e)}")
            raise_error("FILE.FILE_UPLOAD_FAILED")


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
                    auth_types = json.loads(auth.auth_type)
                    # Check whether the passed-in auth_type is in the array
                    result = auth_type in auth_types
                    redis.set(cache_key, auth_type, cache_key_expire)
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
                    raise_error("FILE.VIDEO_INVALID_BILIBILI_LINK")

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
                        raise_error("FILE.VIDEO_BILIBILI_API_ERROR")
                else:
                    raise_error("FILE.VIDEO_BILIBILI_API_REQUEST_FAILED")
            else:
                raise_error("FILE.VIDEO_UNSUPPORTED_VIDEO_SITE")

        except requests.RequestException as e:
            app.logger.error(f"Failed to fetch video info from {url}: {str(e)}")
            raise_error("FILE.VIDEO_NETWORK_ERROR")
        except KeyError as e:
            app.logger.error(f"Missing expected field in API response: {str(e)}")
            raise_error("FILE.VIDEO_PARSE_ERROR")
        except Exception as e:
            app.logger.error(f"Unexpected error getting video info: {str(e)}")
            raise_error("FILE.VIDEO_GET_INFO_ERROR")
