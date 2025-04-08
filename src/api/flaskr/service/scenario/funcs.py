from ...dao import db
from .dtos import ScenarioDto
from ..lesson.models import AICourse
from ...util.uuid import generate_id
from .models import FavoriteScenario
from ..common.dtos import PageNationDTO
from ..common.models import raise_error
from datetime import datetime
from .utils import check_scenario_can_publish
from flaskr.common.config import get_config


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


def get_scenario_info(app, scenario_id: str):
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
