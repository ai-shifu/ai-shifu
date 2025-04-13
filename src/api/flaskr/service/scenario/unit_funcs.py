from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import (
    STATUS_PUBLISH,
    STATUS_DRAFT,
    STATUS_HISTORY,
    STATUS_TO_DELETE,
)
from flaskr.util.uuid import generate_id
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from datetime import datetime
from flaskr.service.scenario.dtos import UnitDto, OutlineDto
from flaskr.service.lesson.const import (
    LESSON_TYPE_TRIAL,
    LESSON_TYPE_NORMAL,
    LESSON_TYPE_BRANCH_HIDDEN,
    SCRIPT_TYPE_SYSTEM,
)
from flaskr.service.scenario.const import UNIT_TYPE_TRIAL, UNIT_TYPE_NORMAL
from sqlalchemy.sql import func, cast
from sqlalchemy import String


def get_unit_list(app, user_id: str, scenario_id: str, chapter_id: str):
    with app.app_context():
        units = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
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
    unit_type: str,
    unit_index: int = 0,
    unit_system_prompt: str = None,
    unit_is_hidden: bool = False,
) -> OutlineDto:
    with app.app_context():
        if len(unit_name) > 20:
            raise_error("SCENARIO.UNIT_NAME_TOO_LONG")
        chapter = AILesson.query.filter(
            AILesson.course_id == scenario_id,
            AILesson.lesson_id == parent_id,
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if chapter:
            existing_unit_count = AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                AILesson.parent_id == parent_id,
            ).count()
            unit_id = generate_id(app)
            if unit_index == 0:
                unit_index = existing_unit_count + 1
            unit_no = chapter.lesson_no + f"{unit_index:02d}"

            app.logger.info(
                f"create unit, user_id: {user_id}, scenario_id: {scenario_id}, parent_id: {parent_id}, unit_no: {unit_no} unit_index: {unit_index}"
            )

            type = LESSON_TYPE_TRIAL
            if unit_type == UNIT_TYPE_NORMAL:
                type = LESSON_TYPE_NORMAL
            elif unit_type == UNIT_TYPE_TRIAL:
                type = LESSON_TYPE_TRIAL

            if unit_is_hidden:
                type = LESSON_TYPE_BRANCH_HIDDEN

            unit = AILesson(
                lesson_id=unit_id,
                lesson_no=unit_no,
                lesson_name=unit_name,
                lesson_desc=unit_description,
                course_id=scenario_id,
                created_user_id=user_id,
                updated_user_id=user_id,
                status=STATUS_DRAFT,
                lesson_index=unit_index,
                lesson_type=type,
                parent_id=parent_id,
            )
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
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

            if unit_system_prompt:
                system_script = AILessonScript.query.filter(
                    AILessonScript.lesson_id == unit_id,
                    AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
                    AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                ).first()

                if not system_script:
                    system_script = AILessonScript(
                        script_id=generate_id(app),
                        lesson_id=unit_id,
                        script_type=SCRIPT_TYPE_SYSTEM,
                        script_prompt=unit_system_prompt,
                        script_name=unit_name + " system prompt",
                        status=STATUS_DRAFT,
                        created_user_id=user_id,
                        updated_user_id=user_id,
                        created=datetime.now(),
                        updated=datetime.now(),
                    )
                    db.session.add(system_script)
                else:
                    system_script.script_prompt = unit_system_prompt
                    system_script.updated = datetime.now()
                    system_script.updated_user_id = user_id

            db.session.add(unit)
            db.session.commit()
            return OutlineDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
                unit_system_prompt,
                unit_is_hidden,
            )
        raise_error("SCENARIO.CHAPTER_NOT_FOUND")


def get_unit_by_id(app, user_id: str, unit_id: str) -> OutlineDto:
    with app.app_context():
        unit = AILesson.query.filter_by(lesson_id=unit_id).first()
        if not unit:
            raise_error("SCENARIO.UNIT_NOT_FOUND")

        unit_type = UNIT_TYPE_NORMAL
        hidden = False
        if unit.lesson_type == LESSON_TYPE_TRIAL:
            unit_type = UNIT_TYPE_TRIAL
        elif unit.lesson_type == LESSON_TYPE_NORMAL:
            unit_type = UNIT_TYPE_NORMAL
        elif unit.lesson_type == LESSON_TYPE_BRANCH_HIDDEN:
            unit_type = UNIT_TYPE_NORMAL
            hidden = True

        system_prompt = None
        system_script = AILessonScript.query.filter(
            AILessonScript.lesson_id == unit_id,
            AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if system_script:
            system_prompt = system_script.script_prompt
        else:
            system_prompt = ""
        return OutlineDto(
            outline_id=unit.lesson_id,
            outline_no=unit.lesson_no,
            outline_name=unit.lesson_name,
            outline_desc=unit.lesson_desc,
            outline_index=unit.lesson_index,
            outline_type=unit_type,
            outline_system_prompt=system_prompt,
            outline_is_hidden=hidden,
        )


# modify unit
def modify_unit(
    app,
    user_id: str,
    unit_id: str,
    unit_name: str = None,
    unit_description: str = None,
    unit_index: int = 0,
    unit_system_prompt: str = None,
    unit_is_hidden: bool = False,
    unit_type: str = UNIT_TYPE_NORMAL,
):
    app.logger.info(
        f"""modify unit, user_id: {user_id}, unit_id: {unit_id}, unit_name: {unit_name},
          unit_description: {unit_description}, unit_index: {unit_index}, unit_system_prompt: {unit_system_prompt},
          unit_is_hidden: {unit_is_hidden}, unit_type: {unit_type}"""
    )
    with app.app_context():
        if unit_name and len(unit_name) > 20:
            raise_error("SCENARIO.UNIT_NAME_TOO_LONG")
        unit = AILesson.query.filter(
            AILesson.lesson_id == unit_id, AILesson.status.in_([STATUS_DRAFT])
        ).first()
        if not unit:
            unit = AILesson.query.filter(
                AILesson.lesson_id == unit_id, AILesson.status.in_([STATUS_PUBLISH])
            ).first()
        if not unit:
            raise_error("SCENARIO.UNIT_NOT_FOUND")
        if unit:
            history_unit = unit.clone()
            if unit_name:
                unit.lesson_name = unit_name
            if unit_description:
                unit.lesson_desc = unit_description
            if unit_index:
                unit.lesson_index = unit_index

            unit.updated_user_id = user_id
            unit.updated_at = datetime.now()
            type = LESSON_TYPE_TRIAL
            if unit_type == UNIT_TYPE_NORMAL:
                type = LESSON_TYPE_NORMAL
            elif unit_type == UNIT_TYPE_TRIAL:
                type = LESSON_TYPE_TRIAL
            if unit_is_hidden:
                type = LESSON_TYPE_BRANCH_HIDDEN

            unit.lesson_type = type
            if not history_unit.eq(unit):
                if history_unit.status != STATUS_PUBLISH:
                    history_unit.status = STATUS_HISTORY
                else:
                    app.logger.info(
                        f"unit is published, history unit: {history_unit.lesson_id} {history_unit.lesson_no}"
                    )
                db.session.add(history_unit)
            unit.status = STATUS_DRAFT
            unit.updated_user_id = user_id
            unit.updated_at = datetime.now()
            if unit_system_prompt:
                system_script = AILessonScript.query.filter(
                    AILessonScript.lesson_id == unit_id,
                    AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
                    AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                ).first()
                if not system_script:
                    system_script = AILessonScript(
                        script_id=generate_id(app),
                        lesson_id=unit_id,
                        script_type=SCRIPT_TYPE_SYSTEM,
                        script_prompt=unit_system_prompt,
                        script_name=unit.lesson_name + " system prompt",
                        status=STATUS_DRAFT,
                        created_user_id=user_id,
                        updated_user_id=user_id,
                        created=datetime.now(),
                        updated=datetime.now(),
                    )
                    db.session.add(system_script)
                elif system_script.script_prompt != unit_system_prompt:
                    history_system_script = system_script.clone()
                    history_system_script.id = None
                    history_system_script.status = STATUS_HISTORY
                    history_system_script.updated_user_id = user_id
                    history_system_script.updated = datetime.now()
                    db.session.add(history_system_script)
                    system_script.script_prompt = unit_system_prompt
                    system_script.updated = datetime.now()
                    system_script.updated_user_id = user_id

            db.session.commit()
            return OutlineDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
                unit_system_prompt,
                unit_is_hidden,
            )
        raise_error("SCENARIO.UNIT_NOT_FOUND")


def delete_unit(app, user_id: str, unit_id: str):
    with app.app_context():
        # check unit is draft
        app.logger.info(f"delete unit: {unit_id}")
        unit = AILesson.query.filter(
            AILesson.lesson_id == unit_id, AILesson.status.in_([STATUS_DRAFT])
        ).first()
        if unit is None:
            unit = AILesson.query.filter(
                AILesson.lesson_id == unit_id, AILesson.status.in_([STATUS_PUBLISH])
            ).first()
        if unit is None:
            raise_error("SCENARIO.UNIT_NOT_FOUND")
        parent_no = ""
        if len(unit.lesson_no) > 2:
            parent_no = unit.lesson_no[:2]
        else:
            parent_no = unit.lesson_no

        if unit.status == STATUS_PUBLISH:
            app.logger.info(
                f"unit is published, prepare to delete: {unit.lesson_id} {unit.lesson_no}"
            )
            prepare_delete_unit = unit.clone()
            app.logger.info(
                f"prepare_delete_unit: {prepare_delete_unit.lesson_id} {prepare_delete_unit.lesson_no} {prepare_delete_unit.lesson_index} {prepare_delete_unit.parent_id}"
            )
            prepare_delete_unit.id = None
            prepare_delete_unit.status = STATUS_TO_DELETE
            prepare_delete_unit.updated_user_id = user_id
            prepare_delete_unit.parent_id = unit.parent_id
            prepare_delete_unit.lesson_no = unit.lesson_no
            prepare_delete_unit.lesson_index = unit.lesson_index
            prepare_delete_unit.course_id = unit.course_id
            prepare_delete_unit.lesson_name = unit.lesson_name
            prepare_delete_unit.lesson_desc = unit.lesson_desc
            prepare_delete_unit.lesson_type = unit.lesson_type
            prepare_delete_unit.updated_at = datetime.now()
            db.session.add(prepare_delete_unit)
        else:
            app.logger.info(
                f"unit is draft, delete unit: {unit.lesson_id} {unit.lesson_no}"
            )
            unit.status = STATUS_TO_DELETE
            unit.updated_user_id = user_id
            parent_no = unit.lesson_no[:2]
        AILesson.query.filter(
            AILesson.course_id == unit.course_id,
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
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
