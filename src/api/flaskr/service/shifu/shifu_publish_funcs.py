from flaskr.framework.plugin.plugin_manager import extension
from flaskr.service.shifu.shifu_draft_funcs import get_latest_shifu_draft
from flaskr.service.common import raise_error
from flaskr.dao import db
from flaskr.service.shifu.models import (
    ShifuPublishedShifu,
    ShifuPublishedOutlineItem,
    ShifuPublishedBlock,
    ShifuDraftOutlineItem,
    ShifuDraftBlock,
    ShifuLogPublishedStruct,
)
from flaskr.util.datetime import get_now_time
from flaskr.service.shifu.shifu_outline_funcs import (
    build_outline_tree,
    ShifuOutlineTreeNode,
)
from flaskr.service.shifu.shifu_block_funcs import __get_block_list_internal
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.common import get_config


@extension("publish_shifu")
def publish_shifu_draft(result, app, user_id: str, shifu_id: str):
    with app.app_context():
        now_time = get_now_time(app)
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        shifu_published = ShifuPublishedShifu()
        shifu_published.shifu_bid = shifu_id
        shifu_published.title = shifu_draft.title
        shifu_published.description = shifu_draft.description
        shifu_published.avatar_res_bid = shifu_draft.avatar_res_bid
        shifu_published.keywords = shifu_draft.keywords
        shifu_published.llm = shifu_draft.llm
        shifu_published.llm_temperature = shifu_draft.llm_temperature
        shifu_published.price = shifu_draft.price
        shifu_published.updated_by_user_bid = user_id
        shifu_published.updated_at = now_time
        db.session.add(shifu_published)
        db.session.flush()
        outline_tree = build_outline_tree(app, shifu_id)

        def publish_outline_item(node: ShifuOutlineTreeNode, history_item: HistoryItem):

            outline_item = ShifuPublishedOutlineItem()
            draft_outline_item: ShifuDraftOutlineItem = node.outline
            outline_item.shifu_bid = shifu_id
            outline_item.outline_item_bid = draft_outline_item.outline_item_bid
            outline_item.title = draft_outline_item.title
            outline_item.position = draft_outline_item.position
            outline_item.type = draft_outline_item.type
            outline_item.hidden = draft_outline_item.hidden
            outline_item.parent_bid = draft_outline_item.parent_bid
            outline_item.llm = draft_outline_item.llm
            outline_item.llm_temperature = draft_outline_item.llm_temperature
            outline_item.llm_system_prompt = draft_outline_item.llm_system_prompt
            outline_item.ask_enabled_status = draft_outline_item.ask_enabled_status
            outline_item.ask_llm = draft_outline_item.ask_llm
            outline_item.ask_llm_temperature = draft_outline_item.ask_llm_temperature
            outline_item.created_user_bid = user_id
            outline_item.created_at = now_time
            outline_item.updated_user_bid = user_id
            outline_item.updated_at = now_time
            outline_item.prerequisite_item_bids = (
                draft_outline_item.prerequisite_item_bids
            )
            db.session.add(outline_item)
            db.session.flush()
            outline_item_history_item = HistoryItem(
                bid=node.outline_id, id=outline_item.id, type="outline", children=[]
            )
            history_item.children.append(outline_item_history_item)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    publish_outline_item(child, outline_item_history_item)
            else:
                draft_blocks: list[ShifuDraftBlock] = __get_block_list_internal(
                    draft_outline_item.outline_item_bid
                )
                for block in draft_blocks:
                    block_item = ShifuPublishedBlock()
                    block_item.shifu_bid = shifu_id
                    block_item.block_bid = block.block_bid
                    block_item.position = block.position
                    block_item.variable_bids = block.variable_bids
                    block_item.resource_bids = block.resource_bids
                    block_item.type = block.type
                    block_item.created_user_bid = user_id
                    block_item.created_at = now_time
                    block_item.updated_user_bid = user_id
                    block_item.updated_at = now_time
                    block_item.outline_item_bid = draft_outline_item.outline_item_bid
                    block_item.content = block.content
                    db.session.add(block_item)
                    db.session.flush()
                    block_history_item = HistoryItem(
                        bid=block.block_bid, id=block_item.id, type="block", children=[]
                    )
                    outline_item_history_item.children.append(block_history_item)
                    db.session.flush()

        history_item = HistoryItem(
            bid=shifu_id, id=shifu_published.id, type="shifu", children=[]
        )
        for node in outline_tree:
            publish_outline_item(node, history_item)

        shifu_log_published_struct = ShifuLogPublishedStruct()
        shifu_log_published_struct.shifu_bid = shifu_id
        shifu_log_published_struct.struct_bid = shifu_id
        shifu_log_published_struct.struct = history_item.to_json()
        shifu_log_published_struct.created_user_bid = user_id
        shifu_log_published_struct.created_at = now_time
        db.session.add(shifu_log_published_struct)

        db.session.commit()
        return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu_id
