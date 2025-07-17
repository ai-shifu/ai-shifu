from flaskr.service.common import raise_error
from flaskr.service.lesson.models import AICourse
from flaskr.service.lesson.const import STATUS_DRAFT
from flaskr.service.shifu.outline_funcs import (
    get_original_outline_tree,
    OutlineTreeNode,
)
from flaskr.service.shifu.shifu_block_funcs import get_block_list as get_block_list_v1
from flaskr.service.shifu.shifu_block_funcs import save_shifu_block_list
from flaskr.framework.plugin.plugin_manager import plugin_manager
from flaskr.service.shifu.models import ShifuDraftShifu, ShifuDraftOutlineItem
from flaskr.util.datetime import get_now_time
from flaskr.dao import db
import queue
from flaskr.service.lesson.models import AILesson
from flaskr.service.lesson.const import (
    LESSON_TYPE_NORMAL,
    LESSON_TYPE_TRIAL,
    LESSON_TYPE_BRANCH_HIDDEN,
)


def migrate_shifu_draft_to_shifu_draft_v2(app, user_id: str, shifu_bid: str):
    with app.app_context():
        plugin_manager.is_enabled = False
        db.session.begin()
        now_time = get_now_time(app)

        old_shifu: AICourse = (
            AICourse.query.filter(
                AICourse.course_id == shifu_bid,
                AICourse.status.nin_([STATUS_DRAFT]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if not old_shifu:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        new_shifu = ShifuDraftShifu()
        new_shifu.shifu_bid = shifu_bid
        new_shifu.title = old_shifu.course_name
        new_shifu.description = old_shifu.course_desc
        new_shifu.avatar_res_bid = old_shifu.course_teacher_avatar
        new_shifu.keywords = old_shifu.course_keywords
        new_shifu.llm = old_shifu.course_default_model
        new_shifu.llm_temperature = old_shifu.course_default_temperature
        new_shifu.price = old_shifu.course_price
        new_shifu.deleted = 0
        new_shifu.created_user_bid = user_id
        new_shifu.updated_by_user_bid = user_id
        new_shifu.created_at = now_time
        new_shifu.updated_at = now_time
        new_shifu.ask_llm = old_shifu.ask_model
        new_shifu.ask_llm_temperature = old_shifu.ask_model_temperature
        new_shifu.ask_llm_system_prompt = old_shifu.ask_prompt
        new_shifu.ask_enabled_status = old_shifu.ask_mode
        new_shifu.ask_llm = old_shifu.ask_model
        new_shifu.ask_llm_temperature = 0.3
        new_shifu.ask_llm_system_prompt = old_shifu.ask_prompt
        new_shifu.ask_enabled_status = old_shifu.ask_mode
        db.session.add(new_shifu)
        db.session.flush()

        outline_tree_v1 = get_original_outline_tree(app, user_id, shifu_bid)
        q = queue.Queue()
        for node in outline_tree_v1:
            q.put(node)
        while not q.empty():
            node: OutlineTreeNode = q.get()
            old_outline: AILesson = node.outline
            new_outline = ShifuDraftOutlineItem()
            new_outline.outline_item_bid = node.outline_id
            new_outline.shifu_bid = shifu_bid

            new_outline.title = old_outline.lesson_name
            new_outline.type = (
                old_outline.lesson_type
                if old_outline.lesson_type == LESSON_TYPE_TRIAL
                else LESSON_TYPE_NORMAL
            )
            new_outline.hidden = (
                old_outline.lesson_type
                if old_outline.lesson_type == LESSON_TYPE_BRANCH_HIDDEN
                else 0
            )
            new_outline.parent_bid = old_outline.parent_id
            new_outline.position = old_outline.lesson_no
            new_outline.prerequisite_item_bids = ""
            new_outline.llm = old_outline.lesson_default_model
            new_outline.llm_temperature = old_outline.lesson_default_temperature
            new_outline.llm_system_prompt = ""
            new_outline.ask_enabled_status = old_outline.ask_mode
            new_outline.ask_llm = old_outline.ask_model
            new_outline.ask_llm_temperature = 0.3
            new_outline.ask_llm_system_prompt = ""
            new_outline.deleted = 0
            new_outline.created_user_bid = user_id
            new_outline.updated_user_bid = user_id
            new_outline.created_at = old_outline.created
            new_outline.updated_at = old_outline.updated
            db.session.add(new_outline)
            db.session.flush()
            if node.children and len(node.children) > 0:
                for child in node.children:
                    q.put(child)
            else:
                block_list_v1 = get_block_list_v1(app, user_id, old_outline.lesson_id)
                json_array = [block.__json__() for block in block_list_v1]
                save_shifu_block_list(
                    None, app, user_id, new_outline.outline_item_bid, json_array
                )

            db.session.commit()

        plugin_manager.is_enabled = True
