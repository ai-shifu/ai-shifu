from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import (
    STATUS_TO_DELETE,
    STATUS_DELETE,
    SCRIPT_TYPE_SYSTEM,
)
from flask import Flask
from flaskr.dao import db


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
    outlines = AILesson.query.filter(AILesson.id.in_(subquery)).all()
    return [
        o
        for o in outlines
        if o.status != STATUS_TO_DELETE and o.status != STATUS_DELETE
    ]


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
        AILessonScript.query.filter(AILessonScript.id.in_(subquery))
        .order_by(AILessonScript.script_index.asc())
        .all()
    )
    return [
        o for o in blocks if o.status != STATUS_TO_DELETE and o.status != STATUS_DELETE
    ]
