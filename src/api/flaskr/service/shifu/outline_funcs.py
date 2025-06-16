from ...dao import db
from ..lesson.models import AILesson
from .dtos import ChapterDto
from sqlalchemy import func
from ...util.uuid import generate_id
from ..common.models import raise_error
from ..lesson.const import (
    LESSON_TYPE_TRIAL,
    STATUS_PUBLISH,
    STATUS_DRAFT,
    STATUS_HISTORY,
)
from datetime import datetime
from .dtos import SimpleOutlineDto
from .utils import (
    get_existing_outlines,
    get_existing_blocks,
    change_outline_status_to_history,
    change_block_status_to_history,
    get_original_outline_tree,
    OutlineTreeNode,
    reorder_outline_tree_and_save,
)
import queue
from flaskr.service.check_risk.funcs import check_text_with_risk_control


# get chapter list
# @author: yfge
# @date: 2025-04-14
# get chapter list will return the chapter list of the shifu
# is used for the shifu outline page in the cook-web
def get_chapter_list(app, user_id: str, shifu_id: str):
    with app.app_context():
        outlines = get_existing_outlines(app, shifu_id)
        chapters = [o for o in outlines if len(o.lesson_no) == 2]
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
# @author: yfge
# @date: 2025-04-14
# create chapter will create a new chapter under the shifu
# and change the lesson_no of the outlines under the chapter
def create_chapter(
    app,
    user_id: str,
    shifu_id: str,
    chapter_name: str,
    chapter_description: str,
    chapter_index: int = 0,
    chapter_type: int = LESSON_TYPE_TRIAL,
):
    with app.app_context():
        outlines = get_existing_outlines(app, shifu_id)
        if next((o for o in outlines if o.lesson_name == chapter_name), None):
            raise_error("SHIFU.CHAPTER_ALREADY_EXISTS")
        existing_chapters = [o for o in outlines if len(o.lesson_no) == 2]
        existing_chapter_count = len(existing_chapters)
        chapter_no = f"{existing_chapter_count + 1:02d}"

        if chapter_index == 0:
            chapter_index = existing_chapter_count + 1
        chapter_id = generate_id(app)
        chapter = AILesson(
            lesson_id=chapter_id,
            lesson_no=chapter_no,
            lesson_name=chapter_name,
            lesson_desc=chapter_description,
            course_id=shifu_id,
            created_user_id=user_id,
            updated_user_id=user_id,
            status=STATUS_DRAFT,
            lesson_index=chapter_index,
            lesson_type=chapter_type,
        )
        check_text_with_risk_control(
            app, chapter_id, user_id, chapter.get_str_to_check()
        )
        db.session.add(chapter)
        for outline in outlines:
            if outline.lesson_no > chapter.lesson_no:
                if outline.lesson_no.startswith(chapter.lesson_no):
                    # delete with the history of the outline
                    # it means the data is dirty
                    if outline.status != STATUS_PUBLISH:
                        outline.status = STATUS_HISTORY
                        outline.updated_user_id = user_id
                        outline.updated_at = datetime.now()
                    continue
                new_outline = outline.clone()
                outline.status = STATUS_HISTORY
                new_outline.status = STATUS_DRAFT
                new_outline.updated_user_id = user_id
                new_outline.updated_at = datetime.now()
                new_chapter_index = int(outline.lesson_no[:2]) - 1
                if len(new_outline.lesson_no) == 2:
                    new_outline.lesson_no = f"{new_chapter_index:02d}"
                else:
                    new_outline.lesson_no = (
                        f"{new_chapter_index:02d}{new_outline.lesson_no[2:]}"
                    )
                app.logger.info(
                    f"reorder outline: {outline.lesson_id} {outline.lesson_no} =>  {new_outline.lesson_no}"
                )
                db.session.add(new_outline)

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
        time = datetime.now()
        chapter = (
            AILesson.query.filter(
                AILesson.lesson_id == chapter_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if chapter:
            chapter.status = STATUS_HISTORY
            new_chapter = chapter.clone()
            new_chapter.lesson_name = chapter_name
            new_chapter.lesson_desc = chapter_description
            new_chapter.updated_user_id = user_id
            new_chapter.lesson_type = chapter_type
            new_chapter.status = STATUS_DRAFT
            new_chapter.lesson_index = chapter_index
            new_chapter.updated_at = datetime.now()
            if chapter_index is not None:
                new_chapter.lesson_index = chapter_index
                db.session.query(AILesson).filter(
                    AILesson.course_id == chapter.course_id,
                    AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                    AILesson.lesson_index >= chapter_index,
                    AILesson.lesson_id != chapter_id,
                ).update(
                    {AILesson.lesson_index: AILesson.lesson_index + 1},
                    synchronize_session=False,
                )
            if new_chapter != chapter:
                change_outline_status_to_history(chapter, user_id, time)
                db.session.add(new_chapter)
            existing_chapter_count = AILesson.query.filter(
                AILesson.course_id == chapter.course_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                func.length(AILesson.lesson_no) == 2,
                AILesson.lesson_id != chapter_id,
                AILesson.lesson_name == chapter_name,
            ).count()
            if existing_chapter_count > 0:
                raise_error("SHIFU.OTHER_SAME_CHAPTER_ALREADY_EXISTS")
            old_check_str = chapter.get_str_to_check()
            new_check_str = new_chapter.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, chapter_id, user_id, new_check_str)
            db.session.commit()
            return ChapterDto(
                chapter.lesson_id,
                chapter.lesson_name,
                chapter.lesson_desc,
                chapter.lesson_type,
            )
        raise_error("SHIFU.CHAPTER_NOT_FOUND")


# delete chapter
# @author: yfge
# @date: 2025-04-14
# delete chapter will also delete all the blocks under the chaper
# and change the lesson_no of the outlines under the chapter
def delete_chapter(app, user_id: str, chapter_id: str):
    with app.app_context():
        time = datetime.now()
        chapter = (
            AILesson.query.filter(
                AILesson.lesson_id == chapter_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        outline_ids = []
        if chapter:
            change_outline_status_to_history(chapter, user_id, time)
            outline_ids.append(chapter.lesson_id)
            outlines = get_existing_outlines(app, chapter.course_id)
            for outline in outlines:
                if outline.lesson_no > chapter.lesson_no:
                    if outline.lesson_no.startswith(chapter.lesson_no):
                        # delete the sub outlines
                        app.logger.info(
                            f"delete outline: {outline.lesson_id} {outline.lesson_no} {outline.lesson_name}"
                        )
                        change_outline_status_to_history(outline, user_id, time)
                        outline_ids.append(outline.lesson_id)
                        continue
                    change_outline_status_to_history(outline, user_id, time)
                    new_outline = outline.clone()
                    new_outline.status = STATUS_DRAFT
                    new_outline.updated_user_id = user_id
                    new_outline.updated_at = time
                    new_chapter_index = int(outline.lesson_no[:2]) - 1
                    if len(new_outline.lesson_no) == 2:
                        new_outline.lesson_no = f"{new_chapter_index:02d}"
                    else:
                        new_outline.lesson_no = (
                            f"{new_chapter_index:02d}{new_outline.lesson_no[2:]}"
                        )
                    app.logger.info(
                        f"reorder outline: {outline.lesson_id} {outline.lesson_no} =>  {new_outline.lesson_no}"
                    )
                    db.session.add(new_outline)
            blocks = get_existing_blocks(app, outline_ids)
            for block in blocks:
                change_block_status_to_history(block, user_id, time)
            db.session.commit()
            return True
        raise_error("SHIFU.CHAPTER_NOT_FOUND")


# update chapter order
# @author: yfge
# @date: 2025-04-14
# update chapter order will also update the lesson_no of the outlines under the chapter
def update_chapter_order(
    app,
    user_id: str,
    shifu_id: str,
    chapter_ids: list,
    move_chapter_id: str,
    move_to_parent_id: str = None,
) -> list[ChapterDto]:
    with app.app_context():
        time = datetime.now()
        outlines = get_original_outline_tree(app, shifu_id)

        # 检查 move_chapter_id 是否存在
        move_chapter = find_node_by_id(outlines, move_chapter_id)
        if not move_chapter:
            raise_error("SHIFU.CHAPTER_NOT_FOUND")

        # 如果提供了 move_to_parent_id，说明是跨章移动
        if move_to_parent_id:
            # 获取目标章节
            target_chapter = find_node_by_id(outlines, move_to_parent_id)
            if not target_chapter:
                raise_error("SHIFU.CHAPTER_NOT_FOUND")

            # 获取目标章节下最大的 lesson_index
            max_index = 0
            for child in target_chapter.children:
                if child.outline.lesson_index > max_index:
                    max_index = child.outline.lesson_index

            # 更新目标章节下所有子节点的 lesson_no
            update_children_lesson_no(
                target_chapter,
                target_chapter.outline.lesson_no,
                max_index,
                user_id,
                time,
            )

            # 重新计算目标章节下最大的 lesson_index
            new_max_index = 0
            for child in target_chapter.children:
                if child.outline.lesson_index > new_max_index:
                    new_max_index = child.outline.lesson_index

            # 保存 move_chapter 的原始信息
            original_parent_id = move_chapter.outline.parent_id
            original_lesson_no = move_chapter.outline.lesson_no
            original_lesson_index = move_chapter.outline.lesson_index

            # 更新 move_chapter 的信息
            move_chapter.outline.parent_id = move_to_parent_id
            move_chapter.outline.lesson_index = new_max_index + 1
            move_chapter.outline.lesson_no = f"{target_chapter.outline.lesson_no}{move_chapter.outline.lesson_index:02d}"
            move_chapter.outline.updated_user_id = user_id
            move_chapter.outline.updated = time
            move_chapter.outline.status = STATUS_DRAFT

            # 将原节点状态改为历史，保留原始信息
            original_outline = move_chapter.outline.clone()
            original_outline.parent_id = original_parent_id
            original_outline.lesson_no = original_lesson_no
            original_outline.lesson_index = original_lesson_index
            original_outline.status = STATUS_HISTORY
            original_outline.updated_user_id = user_id
            original_outline.updated = time
            db.session.add(original_outline)

            # 创建新节点
            new_outline = move_chapter.outline.clone()
            new_outline.status = STATUS_DRAFT
            db.session.add(new_outline)
            move_chapter.outline = new_outline

            # 更新移动章节下所有子节点的 lesson_no
            update_children_lesson_no(
                move_chapter, move_chapter.outline.lesson_no, 0, user_id, time
            )

            # 提交数据库修改
            db.session.commit()

            # 重新获取最新的树结构
            outlines = get_original_outline_tree(app, shifu_id)

        # 构建树结构
        root = OutlineTreeNode(None)
        for outline in outlines:
            root.add_child(outline)
        q = queue.Queue()
        q.put(root)
        # 查找需要重排序的节点
        reorder = False
        while not q.empty():
            node = q.get()
            sub_nodes = node.children
            if len(sub_nodes) == 0:
                continue

            check_in = [
                id
                for id in chapter_ids
                if next((o for o in sub_nodes if o.outline.lesson_id == id), None)
            ]
            if set(check_in) == set(chapter_ids):
                app.logger.info(f"chapter_ids: {chapter_ids} {node.lesson_no}")
                node.children = []
                for id in chapter_ids:
                    node.children.append(
                        next((o for o in sub_nodes if o.outline.lesson_id == id))
                    )
                reorder = True
                break
            for sub_node in sub_nodes:
                q.put(sub_node)

        if reorder:
            reorder_outline_tree_and_save(app, root, user_id, time)
            db.session.commit()
        else:
            raise_error("SHIFU.CHAPTER_IDS_NOT_FOUND")

        return [SimpleOutlineDto(node) for node in outlines]


# get outline tree
# @author: yfge
# @date: 2025-04-14
# get outline tree will return the outline tree of the shifu
# is used for the shifu outline page in the cook-web
def get_outline_tree(app, user_id: str, shifu_id: str):
    with app.app_context():

        outlines = get_original_outline_tree(app, shifu_id)
        outline_tree_dto = [SimpleOutlineDto(node) for node in outlines]
        return outline_tree_dto


def find_node_by_id(nodes, target_id):
    """递归查找指定 ID 的节点

    Args:
        nodes: 节点列表
        target_id: 目标节点 ID

    Returns:
        找到的节点，如果没找到返回 None
    """
    for node in nodes:
        if node.outline.lesson_id == target_id:
            return node
        if node.children:
            found = find_node_by_id(node.children, target_id)
            if found:
                return found
    return None


def update_children_lesson_no(node, parent_lesson_no, start_index, user_id, time):
    """更新节点的所有子节点的 lesson_no

    Args:
        node: 当前节点
        parent_lesson_no: 父节点的 lesson_no
        start_index: 起始索引
        user_id: 用户 ID
        time: 更新时间
    """
    for i, child in enumerate(node.children):
        new_index = start_index + i + 1
        child.outline.lesson_index = new_index
        child.outline.lesson_no = f"{parent_lesson_no}{new_index:02d}"
        child.outline.updated_user_id = user_id
        child.outline.updated = time
        child.outline.status = STATUS_DRAFT

        # 将原节点状态改为历史
        change_outline_status_to_history(child.outline, user_id, time)

        # 创建新节点
        new_child_outline = child.outline.clone()
        new_child_outline.status = STATUS_DRAFT
        db.session.add(new_child_outline)
        child.outline = new_child_outline

        # 递归更新子节点
        update_children_lesson_no(child, child.outline.lesson_no, 0, user_id, time)
