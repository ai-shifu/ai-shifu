from ...dao import db
from datetime import datetime
from .dtos import ScenarioDto, ScenarioDetailDto
from ..lesson.models import AICourse
from ...util.uuid import generate_id
from .models import FavoriteScenario
from ..common.dtos import PageNationDTO


from ..common.models import raise_error, raise_error_with_args
from ...common.config import get_config
from ...service.resource.models import Resource
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
        courses = (
            AICourse.query.filter(AICourse.created_user_id == user_id)
            .order_by(AICourse.id.desc())
            .offset(page_offset)
            .limit(page_size)
            .all()
        )
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
        courses = AICourse.query.filter(AICourse.course_id.in_(course_ids)).all()
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
        if not scenario_description:
            raise_error("SCENARIO.SCENARIO_DESCRIPTION_REQUIRED")
        if len(scenario_name) > 20:
            raise_error("SCENARIO.SCENARIO_NAME_TOO_LONG")
        if len(scenario_description) < 10:
            raise_error("SCENARIO.SCENARIO_DESCRIPTION_TOO_SHORT")
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
            status=0,
            course_keywords=scenario_keywords,
        )
        db.session.add(course)
        db.session.commit()
        return ScenarioDto(
            scenario_id=course_id,
            scenario_name=scenario_name,
            scenario_description=scenario_description,
            scenario_image=scenario_image,
            scenario_state=0,
            is_favorite=False,
        )


def get_scenario_info(app, user_id: str, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter_by(course_id=scenario_id).first()
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
        scenario = AICourse.query.filter_by(course_id=scenario_id).first()
        if scenario:
            return
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def check_scenario_can_publish(app, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter_by(course_id=scenario_id).first()
        if scenario:
            return
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def publish_scenario(app, user_id, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter(AICourse.course_id == scenario_id).first()
        if scenario:
            check_scenario_can_publish(app, scenario_id)
            scenario.status = 1
            scenario.updated_user_id = user_id
            scenario.updated_at = datetime.now()
            db.session.commit()
            return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id
        raise_error("SCENARIO.SCENARIO_NOT_FOUND")


def preview_scenario(app, user_id, scenario_id: str, variables: dict, skip: bool):
    with app.app_context():
        scenario = AICourse.query.filter(AICourse.course_id == scenario_id).first()
        if scenario:
            check_scenario_can_publish(app, scenario_id)
            return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + scenario.course_id


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


def get_scenario_detail(app, scenario_id: str):
    with app.app_context():
        scenario = AICourse.query.filter_by(course_id=scenario_id).first()
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


def save_scenario_detail(
    app,
    user_id: str,
    scenario_id: str,
    scenario_name: str,
    scenario_description: str,
    scenario_teacher_avator: str,
    scenario_keywords: list[str],
    scenario_model: str,
    scenario_price: float,
):
    with app.app_context():
        scenario = AICourse.query.filter_by(course_id=scenario_id).first()
        if scenario:
            scenario.course_name = scenario_name
            scenario.course_desc = scenario_description
            scenario.course_teacher_avator = scenario_teacher_avator
            scenario.course_keywords = ",".join(scenario_keywords)
            scenario.course_default_model = scenario_model
            scenario.course_price = scenario_price
            scenario.updated_user_id = user_id
            scenario.updated_at = datetime.now()
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
