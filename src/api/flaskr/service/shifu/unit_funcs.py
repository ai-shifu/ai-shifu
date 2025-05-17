from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import (
    STATUS_PUBLISH,
    STATUS_DRAFT,
    STATUS_HISTORY,
)
from flaskr.util.uuid import generate_id
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from datetime import datetime
from flaskr.service.shifu.dtos import UnitDto, OutlineDto
from flaskr.service.lesson.const import (
    LESSON_TYPE_TRIAL,
    LESSON_TYPE_NORMAL,
    LESSON_TYPE_BRANCH_HIDDEN,
    SCRIPT_TYPE_SYSTEM,
)
from flaskr.service.shifu.const import UNIT_TYPE_TRIAL, UNIT_TYPE_NORMAL
from sqlalchemy.sql import func, cast
from sqlalchemy import String
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.service.shifu.utils import (
    get_existing_outlines,
    change_outline_status_to_history,
    get_original_outline_tree,
    OutlineTreeNode,
    reorder_outline_tree_and_save,
)

import queue


def get_unit_list(app, user_id: str, shifu_id: str, chapter_id: str):
    with app.app_context():
        existing_outlines = get_existing_outlines(app, shifu_id)
        chapter = next(
            (
                outline
                for outline in existing_outlines
                if outline.lesson_id == chapter_id
            ),
            None,
        )
        if not chapter:
            raise_error("SCENARIO.CHAPTER_NOT_FOUND")
        return [
            UnitDto(
                unit.lesson_id,
                unit.lesson_no,
                unit.lesson_name,
                unit.lesson_desc,
                unit.lesson_type,
            )
            for unit in existing_outlines
            if unit.parent_id == chapter_id
        ]


def create_unit(
    app,
    user_id: str,
    shifu_id: str,
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
        existing_outlines = get_existing_outlines(app, shifu_id)
        chapter = next(
            (
                outline
                for outline in existing_outlines
                if outline.lesson_id == parent_id
            ),
            None,
        )
        if not chapter:
            raise_error("SCENARIO.CHAPTER_NOT_FOUND")

        if chapter:
            app.logger.info(
                f"create unit, user_id: {user_id}, shifu_id: {shifu_id}, parent_id: {parent_id}, unit_index: {unit_index}"
            )
            unit_id = generate_id(app)
            unit_no = chapter.lesson_no + f"{unit_index + 1:02d}"
            app.logger.info(
                f"create unit, user_id: {user_id}, shifu_id: {shifu_id}, parent_id: {parent_id}, unit_no: {unit_no} unit_index: {unit_index}"
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
                course_id=shifu_id,
                created_user_id=user_id,
                updated_user_id=user_id,
                status=STATUS_DRAFT,
                lesson_index=unit_index,
                lesson_type=type,
                parent_id=parent_id,
            )
            check_text_with_risk_control(app, unit_id, user_id, unit.get_str_to_check())
            AILesson.query.filter(
                AILesson.course_id == shifu_id,
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
        unit = (
            AILesson.query.filter(
                AILesson.lesson_id == unit_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
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
        system_script = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == unit_id,
                AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
                AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
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
        unit = (
            AILesson.query.filter(
                AILesson.lesson_id == unit_id,
                AILesson.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not unit:
            raise_error("SCENARIO.UNIT_NOT_FOUND")
        if unit:
            time = datetime.now()
            new_unit = unit.clone()

            old_check_str = unit.get_str_to_check()
            if unit_name:
                new_unit.lesson_name = unit_name
            if unit_description:
                new_unit.lesson_desc = unit_description
            if unit_index:
                new_unit.lesson_index = unit_index

            new_unit.updated_user_id = user_id
            new_unit.updated = time
            type = LESSON_TYPE_TRIAL
            if unit_type == UNIT_TYPE_NORMAL:
                type = LESSON_TYPE_NORMAL
            elif unit_type == UNIT_TYPE_TRIAL:
                type = LESSON_TYPE_TRIAL
            if unit_is_hidden:
                type = LESSON_TYPE_BRANCH_HIDDEN

            new_unit.lesson_type = type
            if not new_unit.eq(unit):
                change_outline_status_to_history(unit, user_id, time)
                new_unit.status = STATUS_DRAFT
                new_unit.updated_user_id = user_id
                new_unit.updated_at = time
                db.session.add(new_unit)
            new_check_str = new_unit.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, unit_id, user_id, new_check_str)
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
                    check_text_with_risk_control(
                        app, unit_id, user_id, system_script.get_str_to_check()
                    )
                    db.session.add(system_script)
                elif system_script.script_prompt != unit_system_prompt:
                    old_check_str = system_script.get_str_to_check()
                    history_system_script = system_script.clone()
                    history_system_script.id = None
                    history_system_script.status = STATUS_HISTORY
                    history_system_script.updated_user_id = user_id
                    history_system_script.updated = datetime.now()
                    db.session.add(history_system_script)
                    system_script.script_prompt = unit_system_prompt
                    system_script.updated = datetime.now()
                    system_script.updated_user_id = user_id
                    new_check_str = system_script.get_str_to_check()
                    if old_check_str != new_check_str:
                        check_text_with_risk_control(
                            app, unit_id, user_id, new_check_str
                        )

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
        time = datetime.now()
        # check unit is draft
        unit = AILesson.query.filter(
            AILesson.lesson_id == unit_id,
            AILesson.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
        ).first()
        outline_tree = get_original_outline_tree(app, unit.course_id)
        q = queue.Queue()
        root = OutlineTreeNode(None)
        for outline in outline_tree:
            root.add_child(outline)
        q.put(root)

        delete_q = queue.Queue()
        while not q.empty():
            node = q.get()
            if node.outline_id == unit_id:
                # to mark the unit as deleted
                delete_q.put(node)
                if node.parent_node:
                    node.parent_node.remove_child(node)
            else:
                for child in node.children:
                    q.put(child)
        # delete the unit and all the children
        delete_unit_ids = []
        while not delete_q.empty():
            node = delete_q.get()
            delete_unit_ids.append(node.outline_id)
            change_outline_status_to_history(node.outline, user_id, time)
            for child in node.children:
                delete_q.put(child)
        # reorder the outline tree
        reorder_outline_tree_and_save(app, root, user_id, time)
        db.session.commit()
