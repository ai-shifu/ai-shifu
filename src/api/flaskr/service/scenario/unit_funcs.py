from flaskr.service.lesson.models import AILesson
from flaskr.util.uuid import generate_id
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from datetime import datetime
from flaskr.service.scenario.dtos import UnitDto, OutlineDto
from flaskr.service.lesson.models import LESSON_TYPE_TRIAL
from sqlalchemy.sql import func, cast
from sqlalchemy import String


def get_unit_list(app, user_id: str, scenario_id: str, chapter_id: str):
    with app.app_context():
        units = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                AILesson.parent_id == chapter_id,
            )
            .order_by(AILesson.lesson_index)
            .all()
        )
        return [
            UnitDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
            )
            for unit in units
        ]


def create_unit(
    app,
    user_id: str,
    scenario_id: str,
    parent_id: str,
    unit_name: str,
    unit_description: str,
    unit_type: int,
    unit_index: int = None,
):
    with app.app_context():
        chapter = AILesson.query.filter(
            AILesson.course_id == scenario_id,
            AILesson.lesson_id == parent_id,
            AILesson.status == 1,
        ).first()
        if chapter:
            existing_unit_count = AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                AILesson.parent_id == parent_id,
            ).count()
            unit_id = generate_id(app)
            if unit_index is None:
                unit_index = existing_unit_count + 1
            unit_no = chapter.lesson_no + f"{unit_index:02d}"

            app.logger.info(
                f"create unit, user_id: {user_id}, scenario_id: {scenario_id}, parent_id: {parent_id}, unit_no: {unit_no} unit_index: {unit_index}"
            )
            unit = AILesson(
                lesson_id=unit_id,
                lesson_no=unit_no,
                lesson_name=unit_name,
                lesson_desc=unit_description,
                course_id=scenario_id,
                created_user_id=user_id,
                updated_user_id=user_id,
                status=1,
                lesson_index=unit_index,
                lesson_type=LESSON_TYPE_TRIAL,
                parent_id=parent_id,
            )
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                AILesson.parent_id == parent_id,
                AILesson.lesson_index >= unit_index,
                AILesson.lesson_id != unit_id,
            ).update(
                {
                    "lesson_index": AILesson.lesson_index + 1,
                    "lesson_no": chapter.lesson_no
                    + func.lpad(cast(AILesson.lesson_index + 1, String), 2, "0"),
                }
            )
            db.session.add(unit)
            db.session.commit()
            return OutlineDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
            )
        raise_error("SCENARIO.CHAPTER_NOT_FOUND")


def modify_unit(
    app,
    user_id: str,
    unit_id: str,
    unit_name: str,
    unit_description: str,
    unit_index: int = None,
):
    with app.app_context():
        unit = AILesson.query.filter_by(lesson_id=unit_id).first()
        if unit:
            unit.lesson_name = unit_name
            unit.lesson_desc = unit_description
            unit.lesson_index = unit_index
            unit.updated_user_id = user_id
            unit.updated_at = datetime.now()
            db.session.commit()
            return UnitDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
            )
        raise_error("SCENARIO.UNIT_NOT_FOUND")


def delete_unit(app, user_id: str, unit_id: str):
    with app.app_context():
        unit = AILesson.query.filter_by(lesson_id=unit_id).first()
        if unit:
            unit.status = 0
            unit.updated_user_id = user_id
            parent_no = unit.lesson_no[:2]
            AILesson.query.filter(
                AILesson.course_id == unit.course_id,
                AILesson.status == 1,
                AILesson.parent_id == unit.parent_id,
                AILesson.lesson_index >= unit.lesson_index,
            ).update(
                {
                    "lesson_index": AILesson.lesson_index - 1,
                    "lesson_no": parent_no
                    + func.lpad(cast(AILesson.lesson_index - 1, String), 2, "0"),
                },
            )
            db.session.commit()
            return True
        raise_error("SCENARIO.UNIT_NOT_FOUND")
