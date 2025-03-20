from ...dao import db
from ..lesson.models import AILesson
from .dtos import ChapterDto
from sqlalchemy import func
from ...util.uuid import generate_id
from ..common.models import raise_error
from ..lesson.models import LESSON_TYPE_TRIAL
from datetime import datetime
from .dtos import SimpleOutlineDto


# get chapter list
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


# create chapter
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


# modify chapter
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
def update_chapter_order(
    app, user_id: str, scenario_id: str, chapter_ids: list
) -> list[ChapterDto]:
    with app.app_context():
        chapter_list = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.lesson_id.in_(chapter_ids),
            )
            .order_by(AILesson.lesson_index.asc(), AILesson.lesson_no.asc())
            .all()
        )

        # check parent no
        parent_no = None
        parent_id = None
        for chapter in chapter_list:
            if parent_no is None:
                parent_no = chapter.lesson_no[:2]
            else:
                if chapter.lesson_no[:2] != parent_no:
                    raise_error("SCENARIO.CHAPTER_PARENT_NO_NOT_MATCH")
            if parent_id is None:
                parent_id = chapter.parent_id
            else:
                if chapter.parent_id != parent_id:
                    raise_error("SCENARIO.CHAPTER_PARENT_ID_NOT_MATCH")
        chapter_dtos = []
        for index, chapter_id in enumerate(chapter_ids):
            chapter = next((c for c in chapter_list if c.lesson_id == chapter_id), None)
            if chapter:
                chapter.lesson_index = index + 1
                chapter.lesson_no = f"{parent_no}{index + 1:02d}"
                chapter.updated_user_id = user_id
                chapter.updated_at = datetime.now()
                chapter_dtos.append(
                    ChapterDto(
                        chapter.lesson_id,
                        chapter.lesson_name,
                        chapter.lesson_desc,
                        chapter.lesson_type,
                    )
                )
        db.session.commit()
        return chapter_dtos


# get outline tree
def get_outline_tree(app, user_id: str, scenario_id: str):
    with app.app_context():
        outline_tree_nodes = (
            AILesson.query.filter(
                AILesson.course_id == scenario_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.lesson_no.asc())
            .all()
        )
        outline_tree_nodes = [
            SimpleOutlineDto(node.lesson_id, node.lesson_no, node.lesson_name)
            for node in outline_tree_nodes
        ]

        # 创建节点字典，用于快速查找
        node_dict = {}

        # 构建树结构
        outline_tree = []

        # 先将所有节点以字典形式存储
        for node in outline_tree_nodes:
            app.logger.info(f"node: {node.__json__()}")
            node_dict[node.outline_no] = node

        # 构建树形结构
        for node in outline_tree_nodes:
            # 如果是顶层节点（lesson_no长度为2）
            if len(node.outline_no) == 2:
                outline_tree.append(node_dict[node.outline_no])
            else:
                # 找到父节点
                parent_no = node.outline_no[:-2]  # 获取父节点的编号
                if parent_no in node_dict and parent_no != node.outline_no:
                    app.logger.info(
                        f"parent_no: {parent_no}, node.outline_no: {node.outline_no}"
                    )
                    node_dict[parent_no].outline_children.append(
                        node_dict[node.outline_no]
                    )
        return outline_tree
