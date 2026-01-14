import json
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import oss2
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkcdn.request.v20180510.DescribeRefreshTasksRequest import (
    DescribeRefreshTasksRequest,
)
from aliyunsdkcdn.request.v20180510.PushObjectCacheRequest import (
    PushObjectCacheRequest,
)

from flaskr.service.common.models import raise_error, raise_error_with_args
from flaskr.service.config import get_config


OSS_PROFILE_DEFAULT = "default"
OSS_PROFILE_COURSES = "courses"

_OSS_CONFIG_KEYS: Mapping[str, Mapping[str, str]] = {
    OSS_PROFILE_DEFAULT: {
        "endpoint": "ALIBABA_CLOUD_OSS_ENDPOINT",
        "access_key_id": "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID",
        "access_key_secret": "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET",
        "base_url": "ALIBABA_CLOUD_OSS_BASE_URL",
        "bucket": "ALIBABA_CLOUD_OSS_BUCKET",
    },
    OSS_PROFILE_COURSES: {
        "endpoint": "ALIBABA_CLOUD_OSS_COURSES_ENDPOINT",
        "access_key_id": "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID",
        "access_key_secret": "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET",
        "base_url": "ALIBABA_CLOUD_OSS_COURSES_URL",
        "bucket": "ALIBABA_CLOUD_OSS_COURSES_BUCKET",
    },
}


@dataclass(frozen=True)
class OSSConfig:
    endpoint: str
    access_key_id: str
    access_key_secret: str
    base_url: str
    bucket: str


def get_oss_config(profile: str = OSS_PROFILE_DEFAULT) -> OSSConfig:
    profile = (profile or "").strip().lower() or OSS_PROFILE_DEFAULT
    keys = _OSS_CONFIG_KEYS.get(profile)
    if not keys:
        raise ValueError(f"Unknown OSS profile: {profile}")

    endpoint = get_config(keys["endpoint"]) or ""
    access_key_id = get_config(keys["access_key_id"]) or ""
    access_key_secret = get_config(keys["access_key_secret"]) or ""
    base_url = get_config(keys["base_url"]) or ""
    bucket = get_config(keys["bucket"]) or ""

    if not access_key_id or not access_key_secret:
        raise_error_with_args(
            "server.api.alibabaCloudNotConfigured",
            config_var=f"{keys['access_key_id']},{keys['access_key_secret']}",
        )

    return OSSConfig(
        endpoint=endpoint,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        base_url=base_url,
        bucket=bucket,
    )


def create_oss_bucket(config: OSSConfig) -> oss2.Bucket:
    auth = oss2.Auth(config.access_key_id, config.access_key_secret)
    return oss2.Bucket(auth, config.endpoint, config.bucket)


def build_oss_url(config: OSSConfig, object_key: str) -> str:
    base = (config.base_url or "").rstrip("/")
    return f"{base}/{object_key}"


def get_image_content_type(filename: str) -> str:
    extension = filename.rsplit(".", 1)[1].lower()
    if extension in ["jpg", "jpeg"]:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    if extension == "gif":
        return "image/gif"
    raise_error("server.file.fileTypeNotSupport")


def warm_up_cdn(app: Any, url: str, config: OSSConfig) -> bool:
    """
    Warm up a CDN URL.
    """
    try:
        region_id = config.endpoint.split(".")[0].replace("oss-", "")
        client = AcsClient(
            config.access_key_id, config.access_key_secret, region_id=region_id
        )
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
                            app.logger.warning(
                                "The image URL is inaccessible. Status code: %s",
                                response.status_code,
                            )
                        except Exception as exc:
                            app.logger.warning(
                                "The image URL access check failed: %s", exc
                            )

                        url_retry_count += 1
                        if url_retry_count < max_url_retries:
                            time.sleep(2)

                    app.logger.warning(
                        "The image URL still cannot be accessed after multiple retries"
                    )
                    return False
                if status == "Failed":
                    app.logger.warning(
                        "The CDN preheating task failed: %s",
                        task.get("Description"),
                    )
                    return False

            retry_count += 1
            if retry_count < max_retries:
                time.sleep(1)

        return False

    except Exception as exc:
        app.logger.warning("CDN preheating failed: %s", exc)
        app.logger.warning("Preheating URL: %s", url)
        app.logger.warning(
            "ObjectPath: %s",
            object_path if "object_path" in locals() else "Not set",
        )
        return False


def upload_to_oss(
    app: Any,
    *,
    file_content: Any,
    file_id: str,
    content_type: str,
    profile: str = OSS_PROFILE_DEFAULT,
    config: Optional[OSSConfig] = None,
    bucket: Optional[oss2.Bucket] = None,
    warm_up: bool = True,
) -> tuple[str, str]:
    resolved_config = config or get_oss_config(profile)
    resolved_bucket = bucket or create_oss_bucket(resolved_config)

    resolved_bucket.put_object(
        file_id,
        file_content,
        headers={"Content-Type": content_type},
    )

    url = build_oss_url(resolved_config, file_id)

    if warm_up:
        warm_up_cdn(app, url, resolved_config)

    return url, resolved_config.bucket
