from ...dao import db
from ..lesson.models import AILesson
from .dtos import ChapterDto, SimpleOutlineDto
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
from .utils import (
    get_existing_outlines,
    get_existing_blocks,
    change_outline_status_to_history,
    mark_outline_to_delete,
    mark_block_to_delete,
    get_original_outline_tree,
    OutlineTreeNode,
    reorder_outline_tree_and_save,
)
import queue
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from .unit_funcs import create_unit
from .dtos import ReorderOutlineItemDto
from .adapter import convert_outline_to_reorder_outline_item_dto


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
        return SimpleOutlineDto(OutlineTreeNode(outline=chapter))


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
            if not new_chapter.eq(chapter):
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
            mark_outline_to_delete(chapter, user_id, time)
            outline_ids.append(chapter.lesson_id)
            outlines = get_existing_outlines(app, chapter.course_id)
            for outline in outlines:
                if outline.lesson_no > chapter.lesson_no:
                    if outline.lesson_no.startswith(chapter.lesson_no):
                        # delete the sub outlines
                        app.logger.info(
                            f"delete outline: {outline.lesson_id} {outline.lesson_no} {outline.lesson_name}"
                        )
                        mark_outline_to_delete(outline, user_id, time)
                        outline_ids.append(outline.lesson_id)
                        continue
                    # reorder the outline
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
                mark_block_to_delete(block, user_id, time)
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

        move_chapter = find_node_by_id(outlines, move_chapter_id)
        if not move_chapter:
            raise_error("SHIFU.CHAPTER_NOT_FOUND")

        is_cross_chapter = False
        if move_to_parent_id:
            target_chapter = find_node_by_id(outlines, move_to_parent_id)
            if not target_chapter:
                raise_error("SHIFU.CHAPTER_NOT_FOUND")
            if (
                move_chapter.parent_node
                and move_chapter.parent_node.outline.lesson_id != move_to_parent_id
            ):
                is_cross_chapter = True

        if is_cross_chapter:
            max_index = 0
            for child in target_chapter.children:
                if child.outline.lesson_index > max_index:
                    max_index = child.outline.lesson_index

            update_children_lesson_no(
                target_chapter,
                target_chapter.outline.lesson_no,
                max_index,
                user_id,
                time,
            )

            new_max_index = 0
            for child in target_chapter.children:
                if child.outline.lesson_index > new_max_index:
                    new_max_index = child.outline.lesson_index

            move_chapter.outline.parent_id = move_to_parent_id
            move_chapter.outline.lesson_index = new_max_index + 1
            move_chapter.outline.lesson_no = f"{target_chapter.outline.lesson_no}{move_chapter.outline.lesson_index:02d}"
            move_chapter.outline.updated_user_id = user_id
            move_chapter.outline.status = STATUS_DRAFT

            change_outline_status_to_history(move_chapter.outline, user_id, time)

            new_outline = move_chapter.outline.clone()
            new_outline.id = 0
            new_outline.status = STATUS_DRAFT
            db.session.add(new_outline)
            move_chapter.outline = new_outline

            update_children_lesson_no(
                move_chapter, move_chapter.outline.lesson_no, 0, user_id, time
            )

            db.session.commit()
            outlines = get_original_outline_tree(app, shifu_id)

        root = OutlineTreeNode(None)
        for outline in outlines:
            root.add_child(outline)
        q = queue.Queue()
        q.put(root)
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
            for id in chapter_ids:
                node = find_node_by_id(outlines, id)
                if node:
                    change_outline_status_to_history(node.outline, user_id, time)
                    new_outline = node.outline.clone()
                    new_outline.status = STATUS_DRAFT
                    new_outline.updated_user_id = user_id
                    new_outline.updated = time
                    node.outline = new_outline
                    db.session.add(new_outline)

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
    for node in nodes:
        if node.outline.lesson_id == target_id:
            return node
        if node.children:
            found = find_node_by_id(node.children, target_id)
            if found:
                return found
    return None


def update_children_lesson_no(node, parent_lesson_no, start_index, user_id, time):
    for i, child in enumerate(node.children):
        new_index = start_index + i + 1
        child.outline.lesson_index = new_index
        child.outline.lesson_no = f"{parent_lesson_no}{new_index:02d}"
        child.outline.updated_user_id = user_id
        child.outline.status = STATUS_DRAFT
        change_outline_status_to_history(child.outline, user_id, time)
        new_child_outline = child.outline.clone()
        new_child_outline.status = STATUS_DRAFT
        db.session.add(new_child_outline)
        child.outline = new_child_outline
        update_children_lesson_no(child, child.outline.lesson_no, 0, user_id, time)


def create_outline(
    app,
    user_id: str,
    shifu_id: str,
    parent_id: str,
    outline_name: str,
    outline_description: str,
    outline_index: int = 0,
    outline_type: int = LESSON_TYPE_TRIAL,
    system_prompt: str = None,
    is_hidden: bool = False,
) -> SimpleOutlineDto:
    if parent_id:
        return create_unit(
            app=app,
            user_id=user_id,
            shifu_id=shifu_id,
            parent_id=parent_id,
            unit_name=outline_name,
            unit_description=outline_description,
            unit_index=outline_index,
            unit_type=outline_type,
            unit_system_prompt=None,
            unit_is_hidden=False,
        )
    else:
        return create_chapter(
            app=app,
            user_id=user_id,
            shifu_id=shifu_id,
            chapter_name=outline_name,
            chapter_description=outline_description,
            chapter_index=outline_index,
            chapter_type=outline_type,
        )


def convert_reorder_outline_item_dto_to_outline_tree(
    outlines: list[ReorderOutlineItemDto], existing_outlines_map: dict[str, AILesson]
):
    ret = []
    for outline in outlines:
        if outline.bid in existing_outlines_map:
            existing_outline = existing_outlines_map[outline.bid]
            node = OutlineTreeNode(existing_outline)
            if outline.children:
                outline_children = convert_reorder_outline_item_dto_to_outline_tree(
                    outline.children, existing_outlines_map
                )
                for child in outline_children:
                    node.add_child(child)
            ret.append(node)
    return ret


def reorder_outline_tree(
    app, user_id: str, shifu_id: str, outlines: list[ReorderOutlineItemDto]
):
    with app.app_context():
        app.logger.info(
            f"reorder outline tree, user_id: {user_id}, shifu_id: {shifu_id}, outlines: {outlines}"
        )
        existing_outlines = get_existing_outlines(app, shifu_id)
        new_outline_tree = convert_outline_to_reorder_outline_item_dto(outlines)
        app.logger.info(f"new_outline_tree: {new_outline_tree}")
        existing_outlines_map = {o.lesson_id: o for o in existing_outlines}
        to_save_outlines = convert_reorder_outline_item_dto_to_outline_tree(
            new_outline_tree, existing_outlines_map
        )
        app.logger.info(f"to_save_outlines: {to_save_outlines}")
        root = OutlineTreeNode(None)
        for outline in to_save_outlines:
            app.logger.info(
                f"add outline: {outline.outline.lesson_id} {outline.outline.lesson_no}"
            )
            root.add_child(outline)
        reorder_outline_tree_and_save(app, root, user_id, datetime.now())
        db.session.commit()
        return True
