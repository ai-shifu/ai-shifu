from ...dao import db
from ..lesson.models import AILesson
from .dtos import ChapterDto
from sqlalchemy import func
from ...util.uuid import generate_id
from ..common.models import raise_error
from ..lesson.models import LESSON_TYPE_TRIAL
from datetime import datetime


def get_chapter_list(app, user_id: str, scenario_id: str):
    with app.app_context():
        chapters = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                func.length(AILesson.lesson_no) == 2,
            )
            .order_by(AILesson.lesson_index.asc(), AILesson.lesson_no.asc())
            .all()
        )
        return [
            ChapterDto(
                chapter.lesson_id,
                chapter.lesson_name,
                chapter.lesson_desc,
                chapter.lesson_type,
            )
            for chapter in chapters
        ]


def create_chapter(
    app,
    user_id: str,
    scenario_id: str,
    chapter_name: str,
    chapter_description: str,
    chapter_index: int = None,
    chapter_type: int = LESSON_TYPE_TRIAL,
):
    with app.app_context():
        existing_chapter = AILesson.query.filter(
            AILesson.course_id == scenario_id,
            AILesson.status == 1,
            AILesson.lesson_name == chapter_name,
        ).first()
        if existing_chapter:
            raise_error("SCENARIO.CHAPTER_ALREADY_EXISTS")
        existing_chapter_count = AILesson.query.filter(
            AILesson.course_id == scenario_id,
            AILesson.status == 1,
            func.length(AILesson.lesson_no) == 2,
        ).count()

        chapter_no = f"{existing_chapter_count + 1:02d}"
        if chapter_index is None:
            chapter_index = existing_chapter_count + 1
        else:
            db.session.query(AILesson).filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                AILesson.lesson_index >= chapter_index,
            ).update(
                {AILesson.lesson_index: AILesson.lesson_index + 1},
                synchronize_session=False,
            )
        chapter_id = generate_id(app)
        chapter = AILesson(
            lesson_id=chapter_id,
            lesson_no=chapter_no,
            lesson_name=chapter_name,
            lesson_desc=chapter_description,
            course_id=scenario_id,
            created_user_id=user_id,
            updated_user_id=user_id,
            status=1,
            lesson_index=chapter_index,
            lesson_type=chapter_type,
        )
        db.session.add(chapter)
        db.session.commit()
        return ChapterDto(
            chapter.lesson_id,
            chapter.lesson_name,
            chapter.lesson_desc,
            chapter.lesson_type,
        )


def modify_chapter(
    app,
    user_id: str,
    chapter_id: str,
    chapter_name: str,
    chapter_description: str,
    chapter_index: int = None,
    chapter_type: int = LESSON_TYPE_TRIAL,
):
    with app.app_context():
        chapter = AILesson.query.filter_by(lesson_id=chapter_id).first()
        if chapter:
            chapter.lesson_name = chapter_name
            chapter.lesson_desc = chapter_description
            chapter.updated_user_id = user_id
            chapter.lesson_type = chapter_type
            existing_chapter_count = AILesson.query.filter(
                AILesson.course_id == chapter.course_id,
                AILesson.status == 1,
                func.length(AILesson.lesson_no) == 2,
                AILesson.lesson_id != chapter_id,
                AILesson.lesson_name == chapter_name,
            ).count()
            if existing_chapter_count > 0:
                raise_error("SCENARIO.OTHER_SAME_CHAPTER_ALREADY_EXISTS")
            if chapter_index is not None:
                chapter.lesson_index = chapter_index
                db.session.query(AILesson).filter(
                    AILesson.course_id == chapter.course_id,
                    AILesson.status == 1,
                    AILesson.lesson_index >= chapter_index,
                    AILesson.lesson_id != chapter_id,
                ).update(
                    {AILesson.lesson_index: AILesson.lesson_index + 1},
                    synchronize_session=False,
                )
            db.session.commit()
            return ChapterDto(
                chapter.lesson_id,
                chapter.lesson_name,
                chapter.lesson_desc,
                chapter.lesson_type,
            )
        raise_error("SCENARIO.CHAPTER_NOT_FOUND")


def delete_chapter(app, user_id: str, chapter_id: str):
    with app.app_context():
        chapter = AILesson.query.filter_by(lesson_id=chapter_id).first()
        if chapter:
            chapter.status = 0
            chapter.updated_user_id = user_id
            db.session.commit()
            return True
        raise_error("SCENARIO.CHAPTER_NOT_FOUND")


# update chapter order
def update_chapter_order(app, user_id: str, scenario_id: str, chapter_ids: list):
    with app.app_context():
        chapter_list = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
                AILesson.lesson_id.in_(chapter_ids),
            )
            .order_by(AILesson.lesson_index.asc(), AILesson.lesson_no.asc())
            .all()
        )
        for index, chapter_id in enumerate(chapter_ids):
            chapter = next((c for c in chapter_list if c.lesson_id == chapter_id), None)
            if chapter:
                chapter.lesson_index = index + 1
                chapter.lesson_no = f"{index + 1:02d}"
                chapter.updated_user_id = user_id
                chapter.updated_at = datetime.now()
        db.session.commit()
        return True
