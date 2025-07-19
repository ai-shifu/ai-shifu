from flaskr.service.lesson.models import AICourse
from flaskr.service.lesson.const import STATUS_DRAFT, STATUS_PUBLISH
from flaskr.service.shifu.outline_funcs import (
    get_original_outline_tree,
    OutlineTreeNode,
)
from flaskr.service.shifu.block_funcs import (
    get_existing_blocks,
    generate_block_dto_from_model,
)
from flaskr.framework.plugin.plugin_manager import plugin_manager
from flaskr.service.shifu.models import (
    ShifuDraftShifu,
    ShifuDraftOutlineItem,
    ShifuDraftBlock,
    ShifuPublishedShifu,
    ShifuPublishedOutlineItem,
    ShifuPublishedBlock,
    ShifuLogPublishedStruct,
)
from flaskr.util import get_now_time, generate_id
from flaskr.dao import db
from flaskr.service.lesson.models import AILesson
from flaskr.service.lesson.const import (
    LESSON_TYPE_NORMAL,
    LESSON_TYPE_TRIAL,
    LESSON_TYPE_BRANCH_HIDDEN,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.profile.profile_manage import get_profile_item_definition_list
from flaskr.service.shifu.adapter import BlockDTO, update_block_dto_to_model_internal
from flaskr.service.shifu.shifu_history_manager import __save_shifu_history
from flaskr.service.lesson.const import SCRIPT_TYPE_SYSTEM
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.shifu.utils import parse_shifu_res_bid


def migrate_shifu_draft_to_shifu_draft_v2(app, shifu_bid: str):
    with app.app_context():
        app.logger.info(
            f"migrate shifu draft to shifu draft v2, shifu_bid: {shifu_bid}"
        )

        plugin_manager.is_enabled = False
        # migrate to draft shifu
        db.session.begin()
        now_time = get_now_time(app)

        old_shifu: AICourse = (
            AICourse.query.filter(
                AICourse.course_id == shifu_bid,
                AICourse.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if not old_shifu:
            app.logger.error(f"shifu not found, shifu_bid: {shifu_bid}")
            return
        user_id = old_shifu.created_user_id
        new_shifu = ShifuDraftShifu()
        new_shifu.shifu_bid = shifu_bid
        new_shifu.title = old_shifu.course_name
        new_shifu.description = old_shifu.course_desc
        new_shifu.avatar_res_bid = parse_shifu_res_bid(old_shifu.course_teacher_avatar)
        new_shifu.keywords = old_shifu.course_keywords
        new_shifu.llm = old_shifu.course_default_model
        new_shifu.llm_temperature = old_shifu.course_default_temperature
        new_shifu.price = old_shifu.course_price
        new_shifu.deleted = 0
        new_shifu.created_user_bid = user_id
        new_shifu.updated_user_bid = user_id
        new_shifu.created_at = now_time
        new_shifu.updated_at = now_time
        new_shifu.ask_llm = old_shifu.ask_model
        new_shifu.ask_llm_temperature = 0.3
        new_shifu.ask_llm_system_prompt = old_shifu.ask_prompt
        new_shifu.ask_enabled_status = old_shifu.ask_mode
        new_shifu.ask_llm = old_shifu.ask_model
        new_shifu.ask_llm_temperature = 0.3
        new_shifu.ask_llm_system_prompt = old_shifu.ask_prompt
        new_shifu.ask_enabled_status = old_shifu.ask_mode
        db.session.add(new_shifu)
        db.session.flush()
        history_item = HistoryItem(
            bid=shifu_bid, id=new_shifu.id, type="shifu", children=[]
        )
        outline_tree_v1 = get_original_outline_tree(app, shifu_bid)
        variable_definitions = get_profile_item_definition_list(app, shifu_bid)

        def migrate_outline(node: OutlineTreeNode, history_item: HistoryItem):
            old_outline: AILesson = node.outline
            app.logger.info(
                f"migrate outline: {old_outline.lesson_id} {old_outline.lesson_no} {old_outline.lesson_name}"
            )

            system_script: AILessonScript = (
                AILessonScript.query.filter(
                    AILessonScript.lesson_id == old_outline.lesson_id,
                    AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
                    AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                )
                .order_by(AILessonScript.id.desc())
                .first()
            )
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
                1 if old_outline.lesson_type == LESSON_TYPE_BRANCH_HIDDEN else 0
            )
            new_outline.parent_bid = old_outline.parent_id
            new_outline.position = old_outline.lesson_no
            new_outline.prerequisite_item_bids = ""
            new_outline.llm = old_outline.lesson_default_model
            new_outline.llm_temperature = old_outline.lesson_default_temperature
            if system_script:
                new_outline.llm_system_prompt = system_script.script_prompt
            else:
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
            outline_history_item = HistoryItem(
                bid=new_outline.outline_item_bid,
                id=new_outline.id,
                type="outline",
                children=[],
            )
            history_item.children.append(outline_history_item)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    migrate_outline(child, outline_history_item)
            else:
                old_blocks = get_existing_blocks(app, [old_outline.lesson_id])
                block_index = 1
                app.logger.info(f"migrate  blocks: {len(old_blocks)}")
                for block in old_blocks:
                    block_dto: BlockDTO = generate_block_dto_from_model(
                        block, variable_definitions
                    )[0]
                    new_block = ShifuDraftBlock()
                    new_block.block_bid = block_dto.bid
                    new_block.outline_item_bid = new_outline.outline_item_bid
                    new_block.position = block_index
                    new_block.deleted = 0
                    new_block.created_at = now_time
                    new_block.created_user_bid = user_id
                    new_block.updated_at = now_time
                    new_block.updated_user_bid = user_id
                    new_block.shifu_bid = shifu_bid
                    result = update_block_dto_to_model_internal(
                        block_dto, new_block, variable_definitions, new_block=True
                    )
                    if result.error_message:
                        app.logger.error(
                            f"Failed to migrate block: {result.error_message}"
                        )
                        continue
                    db.session.add(new_block)
                    db.session.flush()
                    outline_history_item.children.append(
                        HistoryItem(
                            bid=new_block.block_bid,
                            id=new_block.id,
                            type="block",
                            children=[],
                        )
                    )
                    block_index = block_index + 1

        for node in outline_tree_v1:
            migrate_outline(node, history_item)
        __save_shifu_history(app, user_id, shifu_bid, history_item)

        # migrate to publish shifu
        online_course = (
            AICourse.query.filter(
                AICourse.course_id == shifu_bid, AICourse.status.in_([STATUS_PUBLISH])
            )
            .order_by(AICourse.id.desc())
            .first()
        )
        if not online_course:
            app.logger.info(f"no online course, shifu_bid: {shifu_bid}")
            db.session.commit()
            return
        app.logger.info(f"migrate to publish shifu, shifu_bid: {shifu_bid}")
        ShifuPublishedShifu.query.filter(
            ShifuPublishedShifu.shifu_bid == shifu_bid
        ).update({ShifuPublishedShifu.deleted: 1})
        ShifuPublishedOutlineItem.query.filter(
            ShifuPublishedOutlineItem.shifu_bid == shifu_bid
        ).update({ShifuPublishedOutlineItem.deleted: 1})
        ShifuPublishedBlock.query.filter(
            ShifuPublishedBlock.shifu_bid == shifu_bid
        ).update({ShifuPublishedBlock.deleted: 1})
        db.session.flush()
        new_online_course = ShifuPublishedShifu()
        new_online_course.shifu_bid = shifu_bid
        new_online_course.title = new_shifu.title
        new_online_course.description = new_shifu.description
        new_online_course.avatar_res_bid = new_shifu.avatar_res_bid
        new_online_course.keywords = new_shifu.keywords
        new_online_course.llm = new_shifu.llm
        new_online_course.llm_temperature = new_shifu.llm_temperature
        new_online_course.price = new_shifu.price
        new_online_course.deleted = 0
        new_online_course.created_user_bid = user_id
        new_online_course.updated_user_bid = user_id
        new_online_course.created_at = now_time
        new_online_course.updated_at = now_time
        db.session.add(new_online_course)
        db.session.flush()
        history_item = HistoryItem(
            bid=shifu_bid, id=new_online_course.id, type="shifu", children=[]
        )
        __save_shifu_history(app, user_id, shifu_bid, history_item)
        outlines: list[AILesson] = (
            AILesson.query.filter(
                AILesson.course_id == shifu_bid,
                AILesson.status == STATUS_PUBLISH,
            )
            .order_by(AILesson.id.desc())
            .all()
        )
        sorted_outlines = sorted(
            outlines, key=lambda x: (len(x.lesson_no), x.lesson_no)
        )
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
                    app.logger.error(
                        f"Parent node not found for lesson_no: {lesson_no}"
                    )

        def migrate_published_outline(node: OutlineTreeNode, history_item: HistoryItem):

            old_outline: AILesson = node.outline
            app.logger.info(
                f"migrate published outline: {old_outline.lesson_id} {old_outline.lesson_no} {old_outline.lesson_name}"
            )
            system_script: AILessonScript = (
                AILessonScript.query.filter(
                    AILessonScript.lesson_id == old_outline.lesson_id,
                    AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
                    AILessonScript.status == STATUS_PUBLISH,
                )
                .order_by(AILessonScript.id.desc())
                .first()
            )
            new_published_outline = ShifuPublishedOutlineItem()
            new_published_outline.outline_item_bid = node.outline_id
            new_published_outline.shifu_bid = shifu_bid
            new_published_outline.title = old_outline.lesson_name
            new_published_outline.type = old_outline.lesson_type
            new_published_outline.hidden = (
                old_outline.lesson_type == LESSON_TYPE_BRANCH_HIDDEN
            )
            new_published_outline.parent_bid = old_outline.parent_id
            new_published_outline.position = old_outline.lesson_no
            new_published_outline.prerequisite_item_bids = ""
            new_published_outline.llm = old_outline.lesson_default_model
            new_published_outline.llm_temperature = (
                old_outline.lesson_default_temperature
            )
            if system_script:
                new_published_outline.llm_system_prompt = system_script.script_prompt
            else:
                new_published_outline.llm_system_prompt = ""
            new_published_outline.ask_enabled_status = old_outline.ask_mode
            new_published_outline.ask_llm = old_outline.ask_model
            new_published_outline.ask_llm_temperature = 0.3
            new_published_outline.ask_llm_system_prompt = old_outline.ask_prompt
            new_published_outline.deleted = 0
            new_published_outline.created_at = old_outline.created
            new_published_outline.updated_at = old_outline.updated
            new_published_outline.created_user_bid = user_id
            new_published_outline.updated_user_bid = user_id
            db.session.add(new_published_outline)
            db.session.flush()
            outline_history_item = HistoryItem(
                bid=new_published_outline.outline_item_bid,
                id=new_published_outline.id,
                type="outline",
                children=[],
            )
            history_item.children.append(outline_history_item)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    migrate_published_outline(child, outline_history_item)
            else:

                old_blocks = (
                    AILessonScript.query.filter(
                        AILessonScript.lesson_id == old_outline.lesson_id,
                        AILessonScript.script_type != SCRIPT_TYPE_SYSTEM,
                        AILessonScript.status == STATUS_PUBLISH,
                    )
                    .order_by(AILessonScript.script_index.asc())
                    .all()
                )
                block_index = 1
                app.logger.info(f"migrate  blocks: {len(old_blocks)}")
                for block in old_blocks:
                    block_dto: BlockDTO = generate_block_dto_from_model(
                        block, variable_definitions
                    )[0]
                    new_block = ShifuPublishedBlock()
                    new_block.block_bid = block_dto.bid
                    new_block.outline_item_bid = new_published_outline.outline_item_bid
                    new_block.position = block_index
                    new_block.deleted = 0
                    new_block.created_at = now_time
                    new_block.created_user_bid = user_id
                    new_block.updated_at = now_time
                    new_block.updated_user_bid = user_id
                    new_block.shifu_bid = shifu_bid
                    result = update_block_dto_to_model_internal(
                        block_dto, new_block, variable_definitions, new_block=True
                    )
                    if result.error_message:
                        app.logger.error(
                            f"Failed to migrate block: {result.error_message}"
                        )
                        continue
                    db.session.add(new_block)
                    db.session.flush()
                    outline_history_item.children.append(
                        HistoryItem(
                            bid=new_block.block_bid,
                            id=new_block.id,
                            type="block",
                            children=[],
                        )
                    )
                    block_index = block_index + 1

        for node in outline_tree:
            migrate_published_outline(node, history_item)
        shifu_log_published_struct = ShifuLogPublishedStruct()
        shifu_log_published_struct.struct_bid = generate_id(app)
        shifu_log_published_struct.shifu_bid = shifu_bid
        shifu_log_published_struct.struct = history_item.to_json()
        shifu_log_published_struct.created_user_bid = user_id
        shifu_log_published_struct.created_at = now_time
        db.session.add(shifu_log_published_struct)
        db.session.commit()
        plugin_manager.is_enabled = True
