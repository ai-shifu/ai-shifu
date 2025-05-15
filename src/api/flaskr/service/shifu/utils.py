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
import queue


def check_scenario_can_publish(app, scenario_id: str):
    pass


# outline tree node
# @author: yfge
# @date: 2025-04-23
# this is used for the outline tree in the scenario outline page in the cook-web
class OutlineTreeNode:
    outline: AILesson
    children: list["OutlineTreeNode"]
    outline_id: str
    lesson_no: str
    parent_node: "OutlineTreeNode"

    def __init__(self, outline: AILesson):
        self.outline = outline
        self.children = []
        if outline:
            self.outline_id = outline.lesson_id
            self.lesson_no = outline.lesson_no
        else:
            self.outline_id = ""
            self.lesson_no = ""
        self.parent_node = None

    def add_child(self, child: "OutlineTreeNode"):
        self.children.append(child)
        child.parent_node = self

    def remove_child(self, child: "OutlineTreeNode"):
        child.parent_node = None
        self.children.remove(child)

    def get_new_lesson_no(self):
        if not self.parent_node:
            return self.lesson_no
        else:
            return (
                self.parent_node.get_new_lesson_no()
                + f"{self.parent_node.children.index(self) + 1:02d}"
            )


# get the existing outlines for cook
# @author: yfge
# @date: 2025-04-14
def get_existing_outlines(app: Flask, shifu_id: str, parent_id: str = None):
    # with no context, so we need to use the fun n other module
    subquery = (
        db.session.query(db.func.max(AILesson.id))
        .filter(
            AILesson.course_id == shifu_id,
        )
        .group_by(AILesson.lesson_id)
    )
    if parent_id:
        outlines = AILesson.query.filter(
            AILesson.id.in_(subquery),
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            AILesson.parent_id == parent_id,
        ).all()
    else:
        outlines = AILesson.query.filter(
            AILesson.id.in_(subquery),
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).all()
    return sorted(outlines, key=lambda x: (len(x.lesson_no), x.lesson_no))


# get the existing outlines for cook for publish
# @author: yfge
# @date: 2025-04-14
def get_existing_outlines_for_publish(app: Flask, shifu_id: str):
    # with no context, so we need to use the fun in other module
    subquery = (
        db.session.query(db.func.max(AILesson.id))
        .filter(
            AILesson.course_id == shifu_id,
        )
        .group_by(AILesson.lesson_id)
    )
    outlines = AILesson.query.filter(
        AILesson.id.in_(subquery),
        AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT, STATUS_TO_DELETE]),
    ).all()
    app.logger.info(f"get_existing_outlines_for_publish: {len(outlines)}")
    for outline in outlines:
        app.logger.info(
            f"outline: {outline.lesson_no} {outline.lesson_name} {outline.status}"
        )
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

    query = AILessonScript.query.filter(
        AILessonScript.id.in_(subquery),
        AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
    ).order_by(AILessonScript.script_index.asc())

    blocks = query.all()
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
    from flask import current_app as app

    app.logger.info(
        f"change_block_status_to_history: {block_info.id} {block_info.status}"
    )

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


def get_original_outline_tree(app: Flask, shifu_id: str) -> list["OutlineTreeNode"]:
    outlines = get_existing_outlines(app, shifu_id)
    sorted_outlines = sorted(outlines, key=lambda x: (len(x.lesson_no), x.lesson_no))
    outline_tree = []

    nodes_map = {}
    for outline in sorted_outlines:
        node = OutlineTreeNode(outline)
        nodes_map[outline.lesson_no] = node

    # 构建树结构
    for lesson_no, node in nodes_map.items():
        if len(lesson_no) == 2:
            # 这是根节点
            outline_tree.append(node)
        else:
            # 找到父节点的lesson_no
            parent_no = lesson_no[:-2]
            if parent_no in nodes_map:
                parent_node = nodes_map[parent_no]
                # 添加到父节点的children列表中
                if node not in parent_node.children:  # 避免重复添加
                    parent_node.add_child(node)
            else:
                app.logger.error(f"Parent node not found for lesson_no: {lesson_no}")

    return outline_tree


def reorder_outline_tree_and_save(
    app: Flask, tree: "OutlineTreeNode", user_id: str, time: datetime
):
    reorder_queue = queue.Queue()
    reorder_queue.put(tree)
    while not reorder_queue.empty():
        node = reorder_queue.get()
        new_lesson_no = node.get_new_lesson_no()
        app.logger.info(f"reorder outline: {node.lesson_no}=>{new_lesson_no}")
        if new_lesson_no != node.lesson_no:
            change_outline_status_to_history(node.outline, user_id, time)
            app.logger.info(f"reorder unit:{node.lesson_no}=>{new_lesson_no}")
            new_outline = node.outline.clone()
            new_outline.lesson_no = new_lesson_no
            new_outline.updated_user_id = user_id
            new_outline.updated = time
            new_outline.status = STATUS_DRAFT
            node.outline = new_outline
            db.session.add(new_outline)
        for child in node.children:
            reorder_queue.put(child)
