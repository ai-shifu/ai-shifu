from ...dao import db
from datetime import datetime
from .dtos import ScenarioDto, ScenarioDetailDto
from ..lesson.models import AICourse, AILesson, AILessonScript
from ...util.uuid import generate_id
from .models import FavoriteScenario
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


def get_raw_scenario_list(
    app, user_id: str, page_index: int, page_size: int
) -> PageNationDTO:
    try:
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)
        page_offset = (page_index - 1) * page_size
        total = AICourse.query.filter(AICourse.created_user_id == user_id).count()
        subquery = (
            db.session.query(db.func.max(AICourse.id))
            .filter(
                AICourse.created_user_id == user_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .group_by(AICourse.course_id)
        )

        courses = (
            db.session.query(AICourse)
            .filter(AICourse.id.in_(subquery))
            .order_by(AICourse.id.desc())
            .offset(page_offset)
            .limit(page_size)
            .all()
        )
        infos = [f"{c.course_id} + {c.course_name} + {c.status}\r\n" for c in courses]
        app.logger.info(f"{infos}")
        scenario_dtos = [
            ScenarioDto(
                course.course_id,
                course.course_name,
                course.course_desc,
                course.course_teacher_avator,
                course.status,
                False,
            )
            for course in courses
        ]
        return PageNationDTO(page_index, page_size, total, scenario_dtos)
    except Exception as e:
        app.logger.error(f"get raw scenario list failed: {e}")
        return PageNationDTO(0, 0, 0, [])


def get_favorite_scenario_list(
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
        course_ids = [
            favorite_scenario.scenario_id for favorite_scenario in favorite_scenarios
        ]
        courses = AICourse.query.filter(
            AICourse.course_id.in_(course_ids),
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).all()
        scenario_dtos = [
            ScenarioDto(
                course.course_id,
                course.course_name,
                course.course_desc,
                course.course_teacher_avator,
                course.status,
                True,
            )
            for course in courses
        ]
        return PageNationDTO(page_index, page_size, total, scenario_dtos)
    except Exception as e:
        app.logger.error(f"get favorite scenario list failed: {e}")
        return PageNationDTO(0, 0, 0, [])


def get_scenario_list(
    app, user_id: str, page_index: int, page_size: int, is_favorite: bool
) -> PageNationDTO:
    if is_favorite:
        return get_favorite_scenario_list(app, user_id, page_index, page_size)
    else:
        return get_raw_scenario_list(app, user_id, page_index, page_size)


def create_scenario(
    app,
    user_id: str,
    scenario_name: str,
    scenario_description: str,
    scenario_image: str,
    scenario_keywords: list[str] = None,
):
    with app.app_context():
        course_id = generate_id(app)
        if not scenario_name:
            raise_error("SCENARIO.SCENARIO_NAME_REQUIRED")
        if len(scenario_name) > 20:
            raise_error("SCENARIO.SCENARIO_NAME_TOO_LONG")
        if len(scenario_description) > 500:
            raise_error("SCENARIO.SCENARIO_DESCRIPTION_TOO_LONG")
        existing_course = AICourse.query.filter_by(course_name=scenario_name).first()
        if existing_course:
            raise_error("SCENARIO.SCENARIO_NAME_ALREADY_EXISTS")
        course = AICourse(
            course_id=course_id,
            course_name=scenario_name,
            course_desc=scenario_description,
            course_teacher_avator=scenario_image,
            created_user_id=user_id,
            updated_user_id=user_id,
            status=STATUS_DRAFT,
            course_keywords=scenario_keywords,
        )
        check_text_with_risk_control(app, course_id, user_id, course.get_str_to_check())
        db.session.add(course)
        db.session.commit()
        return ScenarioDto(
            scenario_id=course_id,
            scenario_name=scenario_name,
            scenario_description=scenario_description,
            scenario_image=scenario_image,
            scenario_state=STATUS_DRAFT,
            is_favorite=False,
        )


def get_scenario_info(app, user_id: str, scenario_id: str):
    with app.app_context():
        scenario = (
            AICourse.query.filter(
                AICourse.course_id == scenario_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if scenario:
            return ScenarioDto(
                scenario_id=scenario.course_id,
                scenario_name=scenario.course_name,
                scenario_description=scenario.course_desc,
                scenario_image=scenario.course_teacher_avator,
                scenario_state=scenario.status,
                is_favorite=False,
            )
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


# mark favorite scenario
def mark_favorite_scenario(app, user_id: str, scenario_id: str):
    with app.app_context():
        existing_favorite_scenario = FavoriteScenario.query.filter_by(
            scenario_id=scenario_id, user_id=user_id
        ).first()
        if existing_favorite_scenario:
            existing_favorite_scenario.status = 1
            db.session.commit()
            return True
        favorite_scenario = FavoriteScenario(
            scenario_id=scenario_id, user_id=user_id, status=1
        )
        db.session.add(favorite_scenario)
        db.session.commit()
        return True


# unmark favorite scenario
def unmark_favorite_scenario(app, user_id: str, scenario_id: str):
    with app.app_context():
        favorite_scenario = FavoriteScenario.query.filter_by(
            scenario_id=scenario_id, user_id=user_id
        ).first()
        if favorite_scenario:
            favorite_scenario.status = 0
            db.session.commit()
            return True
        return False


def mark_or_unmark_favorite_scenario(
    app, user_id: str, scenario_id: str, is_favorite: bool
):
    if is_favorite:
        return mark_favorite_scenario(app, user_id, scenario_id)
    else:
        return unmark_favorite_scenario(app, user_id, scenario_id)


def check_scenario_exist(app, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter(
            AICourse.course_id == scenario_id,
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if scenario:
            return
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def check_scenario_can_publish(app, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter(
            AICourse.course_id == scenario_id,
            AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if scenario:
            return
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def publish_scenario(app, user_id, scenario_id: str):
    with app.app_context():
        scenario = (
            AICourse.query.filter(
                AICourse.course_id == scenario_id,
                AICourse.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if scenario:
            check_scenario_can_publish(app, scenario_id)
            scenario.status = STATUS_PUBLISH
            scenario.updated_user_id = user_id
            scenario.updated_at = datetime.now()
            # deal with draft lessons
            to_publish_lessons = get_existing_outlines_for_publish(app, scenario_id)
            for to_publish_lesson in to_publish_lessons:
                if to_publish_lesson.status == STATUS_TO_DELETE:
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
                    to_publish_lesson.status = STATUS_PUBLISH
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
                    to_publish_lesson.status = STATUS_PUBLISH
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
                to_publish_lesson.updated_user_id = user_id
                to_publish_lesson.updated = datetime.now()
                db.session.add(to_publish_lesson)
            lesson_ids = [lesson.lesson_id for lesson in to_publish_lessons]
            block_scripts = get_existing_blocks_for_publish(app, lesson_ids)
            if block_scripts:
                for block_script in block_scripts:
                    if block_script.status == STATUS_TO_DELETE:
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

                    elif block_script.status == STATUS_PUBLISH:
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
            return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def preview_scenario(app, user_id, scenario_id: str, variables: dict, skip: bool):
    with app.app_context():
        scenario = AICourse.query.filter(AICourse.course_id == scenario_id).first()
        if scenario:
            check_scenario_can_publish(app, scenario_id)
            return (
                get_config("WEB_URL", "UNCONFIGURED")
                + "/c/"
                + scenario.course_id
                + "?preview=true"
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


def upload_file(app, user_id: str, resource_id: str, file) -> str:
    endpoint = get_config("ALIBABA_CLOUD_OSS_COURSES_ENDPOINT")
    ALI_API_ID = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID", None)
    ALI_API_SECRET = get_config("ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET", None)
    FILE_BASE_URL = get_config("ALIBABA_CLOUD_OSS_COURSES_URL", None)
    BUCKET_NAME = get_config("ALIBABA_CLOUD_OSS_COURSES_BUCKET", None)
    if not ALI_API_ID or not ALI_API_SECRET or ALI_API_ID == "" or ALI_API_SECRET == "":
        app.logger.warning(
            "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID or ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET not configured"
        )
    else:
        auth = oss2.Auth(ALI_API_ID, ALI_API_SECRET)
        bucket = oss2.Bucket(auth, endpoint, BUCKET_NAME)
    with app.app_context():
        if (
            not ALI_API_ID
            or not ALI_API_SECRET
            or ALI_API_ID == ""
            or ALI_API_SECRET == ""
        ):
            raise_error_with_args(
                "API.ALIBABA_CLOUD_NOT_CONFIGURED",
                config_var="ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID,ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET",
            )
        isUpdate = False
        if resource_id == "":
            file_id = str(uuid.uuid4()).replace("-", "")
        else:
            isUpdate = True
            file_id = resource_id
        bucket.put_object(
            file_id,
            file,
            headers={"Content-Type": get_content_type(file.filename)},
        )

        url = FILE_BASE_URL + "/" + file_id
        if isUpdate:
            resource = Resource.query.filter_by(resource_id=file_id).first()
            resource.name = file.filename
            resource.updated_by = user_id
            db.session.commit()
            return url
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


def get_scenario_detail(app, user_id: str, scenario_id: str):
    with app.app_context():
        scenario = (
            AICourse.query.filter(
                AICourse.course_id == scenario_id,
                AICourse.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if scenario:
            keywords = (
                scenario.course_keywords.split(",") if scenario.course_keywords else []
            )
            return ScenarioDetailDto(
                scenario.course_id,
                scenario.course_name,
                scenario.course_desc,
                scenario.course_teacher_avator,
                keywords,
                scenario.course_default_model,
                str(scenario.course_price),
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id,
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id,
            )
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


# save scenario detail
# @author: yfge
# @date: 2025-04-14
# save the scenario detail
def save_scenario_detail(
    app,
    user_id: str,
    scenario_id: str,
    scenario_name: str,
    scenario_description: str,
    scenario_teacher_avatar: str,
    scenario_keywords: list[str],
    scenario_model: str,
    scenario_price: float,
):
    with app.app_context():
        # query scenario
        # the first query is to get the scenario latest record
        scenario = (
            AICourse.query.filter_by(course_id=scenario_id)
            .order_by(AICourse.id.desc())
            .first()
        )
        if scenario:
            old_check_str = scenario.get_str_to_check()
            new_scenario = scenario.clone()
            new_scenario.course_name = scenario_name
            new_scenario.course_desc = scenario_description
            new_scenario.course_teacher_avator = scenario_teacher_avatar
            new_scenario.course_keywords = ",".join(scenario_keywords)
            new_scenario.course_default_model = scenario_model
            new_scenario.course_price = scenario_price
            new_scenario.updated_user_id = user_id
            new_scenario.updated_at = datetime.now()
            new_check_str = new_scenario.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, scenario_id, user_id, new_check_str)
            if not scenario.eq(new_scenario):
                new_scenario.status = STATUS_DRAFT
                if scenario.status == STATUS_DRAFT:
                    # if scenario is draft, history it
                    # if scenario is publish,so DO NOTHING
                    scenario.status = STATUS_HISTORY
                db.session.add(new_scenario)
            db.session.commit()
            return ScenarioDetailDto(
                scenario.course_id,
                scenario.course_name,
                scenario.course_desc,
                scenario.course_teacher_avator,
                scenario.course_keywords,
                scenario.course_default_model,
                str(scenario.course_price),
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id,
                get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id,
            )
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")
