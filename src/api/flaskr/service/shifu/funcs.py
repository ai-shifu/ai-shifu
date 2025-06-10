from ...dao import redis_client as redis, db
from datetime import datetime
from .dtos import ShifuDto, ShifuDetailDto
from ..lesson.models import AICourse, AILesson, AILessonScript
from ...util.uuid import generate_id
from .models import FavoriteScenario, AiCourseAuth
from ..common.dtos import PageNationDTO
from ...service.lesson.const import (
    STATUS_PUBLISH,
    STATUS_DRAFT,
    STATUS_DELETE,
    STATUS_HISTORY,
    STATUS_TO_DELETE,
)
from ..check_risk.funcs import check_text_with_risk_control
from ..common.models import raise_error, raise_error_with_args
from ...common.config import get_config
from ...service.resource.models import Resource
from .utils import get_existing_outlines_for_publish, get_existing_blocks_for_publish
import oss2
import uuid
import json
import requests
from io import BytesIO
from urllib.parse import urlparse
import re
import time


def get_raw_shifu_list(
    app, user_id: str, page_index: int, page_size: int
) -> PageNationDTO:
    try:
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)
        page_offset = (page_index - 1) * page_size

        created_total = AICourse.query.filter(AICourse.created_user_id == user_id).count()
        shared_total = AiCourseAuth.query.filter(
            AiCourseAuth.user_id == user_id,
        ).count()
        total = created_total + shared_total

        created_subquery = (
            db.session.query(db.func.max(AICourse.id))
            .filter(
                AICourse.created_user_id == user_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .group_by(AICourse.course_id)
        )

        shared_course_ids = db.session.query(AiCourseAuth.course_id).filter(
            AiCourseAuth.user_id == user_id
        ).subquery()

        shared_subquery = (
            db.session.query(db.func.max(AICourse.id))
            .filter(
                AICourse.course_id.in_(shared_course_ids),
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .group_by(AICourse.course_id)
        )

        union_subquery = created_subquery.union(shared_subquery).subquery()

        courses = (
            db.session.query(AICourse)
            .filter(AICourse.id.in_(union_subquery))
            .order_by(AICourse.id.desc())
            .offset(page_offset)
            .limit(page_size)
            .all()
        )

        infos = [f"{c.course_id} + {c.course_name} + {c.status}\r\n" for c in courses]
        app.logger.info(f"{infos}")
        shifu_dtos = [
            ShifuDto(
                course.course_id,
                course.course_name,
                course.course_desc,
                course.course_teacher_avator,
                course.status,
                False,
            )
            for course in courses
        ]
        return PageNationDTO(page_index, page_size, total, shifu_dtos)
    except Exception as e:
        app.logger.error(f"get raw shifu list failed: {e}")
        return PageNationDTO(0, 0, 0, [])


def get_favorite_shifu_list(
    app, user_id: str, page_index: int, page_size: int
) -> PageNationDTO:
    try:
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)
        page_offset = (page_index - 1) * page_size
        total = FavoriteScenario.query.filter(
            FavoriteScenario.user_id == user_id
        ).count()
        favorite_scenarios = (
            FavoriteScenario.query.filter(FavoriteScenario.user_id == user_id)
            .order_by(FavoriteScenario.id.desc())
            .offset(page_offset)
            .limit(page_size)
            .all()
        )
        shifu_ids = [
            favorite_scenario.scenario_id for favorite_scenario in favorite_scenarios
        ]
        courses = AICourse.query.filter(
            AICourse.course_id.in_(shifu_ids),
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).all()
        shifu_dtos = [
            ShifuDto(
                course.course_id,
                course.course_name,
                course.course_desc,
                course.course_teacher_avator,
                course.status,
                True,
            )
            for course in courses
        ]
        return PageNationDTO(page_index, page_size, total, shifu_dtos)
    except Exception as e:
        app.logger.error(f"get favorite shifu list failed: {e}")
        return PageNationDTO(0, 0, 0, [])


def get_shifu_list(
    app, user_id: str, page_index: int, page_size: int, is_favorite: bool
) -> PageNationDTO:
    if is_favorite:
        return get_favorite_shifu_list(app, user_id, page_index, page_size)
    else:
        return get_raw_shifu_list(app, user_id, page_index, page_size)


def create_shifu(
    app,
    user_id: str,
    shifu_name: str,
    shifu_description: str,
    shifu_image: str,
    shifu_keywords: list[str] = None,
):
    with app.app_context():
        shifu_id = generate_id(app)
        if not shifu_name:
            raise_error("SHIFU.SHIFU_NAME_REQUIRED")
        if len(shifu_name) > 20:
            raise_error("SHIFU.SHIFU_NAME_TOO_LONG")
        if len(shifu_description) > 500:
            raise_error("SHIFU.SHIFU_DESCRIPTION_TOO_LONG")
        existing_shifu = AICourse.query.filter_by(course_name=shifu_name).first()
        if existing_shifu:
            raise_error("SHIFU.SHIFU_NAME_ALREADY_EXISTS")
        course = AICourse(
            course_id=shifu_id,
            course_name=shifu_name,
            course_desc=shifu_description,
            course_teacher_avator=shifu_image,
            created_user_id=user_id,
            updated_user_id=user_id,
            status=STATUS_DRAFT,
            course_keywords=shifu_keywords,
        )
        check_text_with_risk_control(app, shifu_id, user_id, course.get_str_to_check())
        db.session.add(course)
        db.session.commit()
        return ShifuDto(
            shifu_id=shifu_id,
            shifu_name=shifu_name,
            shifu_description=shifu_description,
            shifu_avatar=shifu_image,
            shifu_state=STATUS_DRAFT,
            is_favorite=False,
        )


def get_shifu_info(app, user_id: str, shifu_id: str):
    with app.app_context():
        shifu = (
            AICourse.query.filter(
                AICourse.course_id == shifu_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if shifu:
            return ShifuDetailDto(
                shifu_id=shifu.course_id,
                shifu_name=shifu.course_name,
                shifu_description=shifu.course_desc,
                shifu_avatar=shifu.course_teacher_avator,
                shifu_keywords=(
                    shifu.course_keywords.split(",") if shifu.course_keywords else []
                ),
                shifu_model=shifu.course_default_model,
                shifu_price=shifu.course_price,
                shifu_url=get_config("WEB_URL", "UNCONFIGURED")
                + "/c/"
                + shifu.course_id,
                shifu_preview_url=get_config("WEB_URL", "UNCONFIGURED")
                + "/c/"
                + shifu.course_id
                + "?preview=true",
            )
        raise_error("SHIFU.SHIFU_NOT_FOUND")


# mark favorite shifu
def mark_favorite_shifu(app, user_id: str, shifu_id: str):
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
    if is_favorite:
        return mark_favorite_shifu(app, user_id, shifu_id)
    else:
        return unmark_favorite_shifu(app, user_id, shifu_id)


def check_shifu_exist(app, shifu_id: str):
    with app.app_context():
        shifu = AICourse.query.filter(
            AICourse.course_id == shifu_id,
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if shifu:
            return
        raise_error("SHIFU.SHIFU_NOT_FOUND")


def check_shifu_can_publish(app, shifu_id: str):
    with app.app_context():
        shifu = AICourse.query.filter(
            AICourse.course_id == shifu_id,
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if shifu:
            return
        raise_error("SHIFU.SHIFU_NOT_FOUND")


def publish_shifu(app, user_id, shifu_id: str):
    with app.app_context():
        shifu = (
            AICourse.query.filter(
                AICourse.course_id == shifu_id,
                AICourse.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if shifu:
            check_shifu_can_publish(app, shifu_id)
            shifu.status = STATUS_PUBLISH
            shifu.updated_user_id = user_id
            shifu.updated_at = datetime.now()
            # deal with draft lessons
            to_publish_lessons = get_existing_outlines_for_publish(app, shifu_id)
            for to_publish_lesson in to_publish_lessons:
                if to_publish_lesson.status == STATUS_TO_DELETE:
                    # delete the lesson
                    to_publish_lesson.status = STATUS_DELETE
                    AILesson.query.filter(
                        AILesson.lesson_id == to_publish_lesson.lesson_id,
                        AILesson.status.in_([STATUS_PUBLISH]),
                    ).update(
                        {
                            "status": STATUS_DELETE,
                            "updated_user_id": user_id,
                            "updated": datetime.now(),
                        }
                    )
                elif to_publish_lesson.status == STATUS_PUBLISH:
                    # change the lesson status to history
                    # these logic would be removed in the future
                    AILesson.query.filter(
                        AILesson.lesson_id == to_publish_lesson.lesson_id,
                        AILesson.status.in_([STATUS_PUBLISH]),
                        AILesson.id != to_publish_lesson.id,
                    ).update(
                        {
                            "status": STATUS_HISTORY,
                            "updated_user_id": user_id,
                            "updated": datetime.now(),
                        }
                    )

                elif to_publish_lesson.status == STATUS_DRAFT:
                    # create a new lesson to publish
                    new_lesson = to_publish_lesson.clone()
                    new_lesson.status = STATUS_PUBLISH
                    new_lesson.updated_user_id = user_id
                    new_lesson.updated = datetime.now()
                    db.session.add(new_lesson)
                    # change the lesson status to history
                    AILesson.query.filter(
                        AILesson.lesson_id == to_publish_lesson.lesson_id,
                        AILesson.status.in_([STATUS_PUBLISH]),
                        AILesson.id < to_publish_lesson.id,
                    ).update(
                        {
                            "status": STATUS_HISTORY,
                            "updated_user_id": user_id,
                            "updated": datetime.now(),
                        }
                    )

            lesson_ids = [lesson.lesson_id for lesson in to_publish_lessons]
            block_scripts = get_existing_blocks_for_publish(app, lesson_ids)
            if block_scripts:
                for block_script in block_scripts:
                    if block_script.status == STATUS_TO_DELETE:
                        # delete the block script
                        block_script.status = STATUS_DELETE
                        AILessonScript.query.filter(
                            AILessonScript.script_id == block_script.script_id,
                            AILessonScript.status.in_([STATUS_PUBLISH]),
                        ).update(
                            {
                                "status": STATUS_DELETE,
                                "updated_user_id": user_id,
                                "updated": datetime.now(),
                            }
                        )

                    elif block_script.status == STATUS_DRAFT:
                        # create a new block script to publish
                        new_block_script = block_script.clone()
                        new_block_script.status = STATUS_PUBLISH
                        new_block_script.updated_user_id = user_id
                        new_block_script.updated = datetime.now()
                        db.session.add(new_block_script)
                        # change the block status to history
                        AILessonScript.query.filter(
                            AILessonScript.script_id == block_script.script_id,
                            AILessonScript.status.in_([STATUS_PUBLISH]),
                            AILessonScript.id < block_script.id,
                        ).update(
                            {
                                "status": STATUS_HISTORY,
                                "updated_user_id": user_id,
                                "updated": datetime.now(),
                            }
                        )

                    elif block_script.status == STATUS_PUBLISH:
                        # if the block is publish, then we need to change the status to history
                        # these logic would be removed in the future
                        block_script.status = STATUS_PUBLISH
                        AILessonScript.query.filter(
                            AILessonScript.script_id == block_script.script_id,
                            AILessonScript.status.in_([STATUS_PUBLISH]),
                            AILessonScript.id != block_script.id,
                        ).update(
                            {
                                "status": STATUS_HISTORY,
                                "updated_user_id": user_id,
                                "updated": datetime.now(),
                            }
                        )
                    block_script.updated_user_id = user_id
                    block_script.updated = datetime.now()
                    db.session.add(block_script)
            db.session.commit()
            return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu.course_id
        raise_error("SHIFU.SHIFU_NOT_FOUND")


def preview_shifu(app, user_id, shifu_id: str, variables: dict, skip: bool):
    with app.app_context():
        shifu = AICourse.query.filter(AICourse.course_id == shifu_id).first()
        if shifu:
            check_shifu_can_publish(app, shifu_id)
            return (
                get_config("WEB_URL", "UNCONFIGURED")
                + "/c/"
                + shifu.course_id
                + "?preview=true"
                + "&skip="
                + str(skip).lower()
            )


def get_content_type(filename):
    extension = filename.rsplit(".", 1)[1].lower()
    if extension in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif extension == "png":
        return "image/png"
    elif extension == "gif":
        return "image/gif"
    raise_error("FILE.FILE_TYPE_NOT_SUPPORT")


def _warm_up_cdn(app, url: str, ALI_API_ID: str, ALI_API_SECRET: str, endpoint: str):
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcdn.request.v20180510.PushObjectCacheRequest import (
            PushObjectCacheRequest,
        )
        from aliyunsdkcdn.request.v20180510.DescribeRefreshTasksRequest import (
            DescribeRefreshTasksRequest,
        )
        import json
        import requests

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
        app.logger.warning(f"CDN预热失败: {str(e)}")
        app.logger.warning(f"预热URL: {url}")
        app.logger.warning(
            f"ObjectPath: {object_path if 'object_path' in locals() else 'Not set'}"
        )
        return False


def _upload_to_oss(app, file_content, file_id: str, content_type: str) -> str:
    endpoint = get_config("ALIBABA_CLOUD_OSS_COURSES_ENDPOINT")
    ALI_API_ID = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID", None)
    ALI_API_SECRET = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET", None)
    FILE_BASE_URL = get_config("ALIBABA_CLOUD_OSS_COURSES_URL", None)
    BUCKET_NAME = get_config("ALIBABA_CLOUD_OSS_COURSES_BUCKET", None)

    if not ALI_API_ID or not ALI_API_SECRET or ALI_API_ID == "" or ALI_API_SECRET == "":
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


def get_shifu_detail(app, user_id: str, shifu_id: str):
    with app.app_context():
        shifu = (
            AICourse.query.filter(
                AICourse.course_id == shifu_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if shifu:
            keywords = shifu.course_keywords.split(",") if shifu.course_keywords else []
            return ShifuDetailDto(
                shifu.course_id,
                shifu.course_name,
                shifu.course_desc,
                shifu.course_teacher_avator,
                keywords,
                shifu.course_default_model,
                str(shifu.course_price),
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu.course_id,
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu.course_id,
            )
        raise_error("SHIFU.SHIFU_NOT_FOUND")


# save shifu detail
# @author: yfge
# @date: 2025-04-14
# save the shifu detail
def save_shifu_detail(
    app,
    user_id: str,
    shifu_id: str,
    shifu_name: str,
    shifu_description: str,
    shifu_avatar: str,
    shifu_keywords: list[str],
    shifu_model: str,
    shifu_price: float,
):
    with app.app_context():
        # query shifu
        # the first query is to get the shifu latest record
        shifu = (
            AICourse.query.filter_by(course_id=shifu_id)
            .order_by(AICourse.id.desc())
            .first()
        )
        if shifu:
            old_check_str = shifu.get_str_to_check()
            new_shifu = shifu.clone()
            new_shifu.course_name = shifu_name
            new_shifu.course_desc = shifu_description
            new_shifu.course_teacher_avator = shifu_avatar
            new_shifu.course_keywords = ",".join(shifu_keywords)
            new_shifu.course_default_model = shifu_model
            new_shifu.course_price = shifu_price
            new_shifu.updated_user_id = user_id
            new_shifu.updated_at = datetime.now()
            new_check_str = new_shifu.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, shifu_id, user_id, new_check_str)
            if not shifu.eq(new_shifu):
                new_shifu.status = STATUS_DRAFT
                if shifu.status == STATUS_DRAFT:
                    # if shifu is draft, history it
                    # if shifu is publish,so DO NOTHING
                    shifu.status = STATUS_HISTORY
                db.session.add(new_shifu)
            db.session.commit()
            return ShifuDetailDto(
                shifu.course_id,
                shifu.course_name,
                shifu.course_desc,
                shifu.course_teacher_avator,
                shifu.course_keywords,
                shifu.course_default_model,
                str(shifu.course_price),
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu.course_id,
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu.course_id,
            )
        raise_error("SHIFU.SHIFU_NOT_FOUND")


def shifu_permission_verification(
    app,
    user_id: str,
    shifu_id: str,
    auth_type: str,
):
    with app.app_context():
        cache_key = (
            get_config("REDIS_KEY_PREFIX", "ai-shifu:")
            + "shifu_permission:"
            + user_id
            + ":"
            + shifu_id
        )
        cache_key_expire = int(get_config("SHIFU_PERMISSION_CACHE_EXPIRE", "1"))
        cache_result = redis.get(cache_key)
        if cache_result is not None:
            try:
                cached_auth_types = json.loads(cache_result)
                return auth_type in cached_auth_types
            except (json.JSONDecodeError, TypeError):
                redis.delete(cache_key)
        # If it is not in the cache, query the database
        shifu = AICourse.query.filter(
            AICourse.course_id == shifu_id, AICourse.created_user_id == user_id
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
                    redis.set(cache_key, auth.auth_type, cache_key_expire)
                    return result
                except (json.JSONDecodeError, TypeError):
                    return False
            else:
                return False


def get_video_info(app, user_id: str, url: str) -> dict:
    """
    Obtain video information
    """
    with app.app_context():
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            if "bilibili.com" in domain:
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
