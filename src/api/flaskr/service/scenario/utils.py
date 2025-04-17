from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import (
    STATUS_PUBLISH,
    STATUS_DRAFT,
    SCRIPT_TYPE_SYSTEM,
    STATUS_HISTORY,
    STATUS_TO_DELETE,
)
from flask import Flask
from flaskr.dao import db
from datetime import datetime


def check_scenario_can_publish(app, scenario_id: str):
    pass


# get the existing outlines for cook
# @author: yfge
# @date: 2025-04-14
def get_existing_outlines(app: Flask, scenario_id: str):
    # with no context, so we need to use the fun in other module
    subquery = (
        db.session.query(db.func.max(AILesson.id))
        .filter(
            AILesson.course_id == scenario_id,
        )
        .group_by(AILesson.lesson_id)
    )
    outlines = AILesson.query.filter(
        AILesson.id.in_(subquery),
        AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
    ).all()
    return outlines


# get the existing outlines for cook for publish
# @author: yfge
# @date: 2025-04-14
def get_existing_outlines_for_publish(app: Flask, scenario_id: str):
    # with no context, so we need to use the fun in other module
    subquery = (
        db.session.query(db.func.max(AILesson.id))
        .filter(
            AILesson.course_id == scenario_id,
        )
        .group_by(AILesson.lesson_id)
    )
    outlines = AILesson.query.filter(
        AILesson.id.in_(subquery),
        AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT, STATUS_TO_DELETE]),
    ).all()
    return outlines


# get the existing blocks for cook
# @author: yfge
# @date: 2025-04-14
def get_existing_blocks(app: Flask, outline_ids: list[str]):
    # get the existing blocks (publish and draft)
    subquery = (
        db.session.query(db.func.max(AILessonScript.id))
        .filter(
            AILessonScript.lesson_id.in_(outline_ids),
            AILessonScript.script_type != SCRIPT_TYPE_SYSTEM,
        )
        .group_by(AILessonScript.script_id)
    )
    blocks = (
        AILessonScript.query.filter(
            AILessonScript.id.in_(subquery),
            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        )
        .order_by(AILessonScript.script_index.asc())
        .all()
    )
    return blocks


# get the existing blocks for cook for publish
# @author: yfge
# @date: 2025-04-14
def get_existing_blocks_for_publish(app: Flask, outline_ids: list[str]):
    # get the existing blocks (publish and draft)
    subquery = (
        db.session.query(db.func.max(AILessonScript.id))
        .filter(
            AILessonScript.lesson_id.in_(outline_ids),
        )
        .group_by(AILessonScript.script_id)
    )
    blocks = (
        AILessonScript.query.filter(
            AILessonScript.id.in_(subquery),
            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT, STATUS_TO_DELETE]),
        )
        .order_by(AILessonScript.script_index.asc())
        .all()
    )
    return blocks


# change the outline status to history
# @author: yfge
# @date: 2025-04-14
def change_outline_status_to_history(
    outline_info: AILesson, user_id: str, time: datetime
):
    if outline_info.status != STATUS_PUBLISH:
        # if the outline is not publish, then we need to change the status to history
        outline_info.status = STATUS_HISTORY
        outline_info.updated_user_id = user_id
        outline_info.updated = time
    else:
        new_outline = outline_info.clone()
        new_outline.status = STATUS_TO_DELETE
        new_outline.updated_user_id = user_id
        new_outline.updated = time
        db.session.add(new_outline)


# change the block status to history
# @author: yfge
# @date: 2025-04-14
def change_block_status_to_history(
    block_info: AILessonScript, user_id: str, time: datetime
):
    if block_info.status != STATUS_PUBLISH:
        # if the block is not publish, then we need to change the status to history
        block_info.status = STATUS_HISTORY
        block_info.updated_user_id = user_id
        block_info.updated = time
    else:
        new_block = block_info.clone()
        new_block.status = STATUS_TO_DELETE
        new_block.updated_user_id = user_id
        new_block.updated = time
        db.session.add(new_block)
