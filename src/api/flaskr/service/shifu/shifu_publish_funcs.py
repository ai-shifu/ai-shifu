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
from flaskr.service.shifu.shifu_outline_funcs import (
    build_outline_tree,
    ShifuOutlineTreeNode,
)
from flaskr.service.shifu.shifu_block_funcs import __get_block_list_internal
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_struct_manager import get_shifu_outline_tree
from flaskr.common import get_config
from flaskr.util import generate_id
from datetime import datetime
import json
import threading
from collections import defaultdict
import queue
from flaskr.service.shifu.shifu_struct_manager import ShifuInfoDto
from flaskr.api.llm import invoke_llm
from flaskr.api.langfuse import langfuse_client
from flaskr.util.prompt_loader import load_prompt_template
from flaskr.service.shifu.consts import (
    ASK_MODE_ENABLE,
    BLOCK_TYPE_CONTENT_VALUE,
)


@extension("publish_shifu")
def publish_shifu_draft(result, app, user_id: str, shifu_id: str):
    with app.app_context():
        now_time = datetime.now()
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        ShifuPublishedShifu.query.filter_by(shifu_bid=shifu_id).update({"deleted": 1})
        ShifuPublishedOutlineItem.query.filter_by(shifu_bid=shifu_id).update(
            {"deleted": 1}
        )
        ShifuPublishedBlock.query.filter_by(shifu_bid=shifu_id).update({"deleted": 1})
        shifu_published = ShifuPublishedShifu()
        shifu_published.shifu_bid = shifu_id
        shifu_published.title = shifu_draft.title
        shifu_published.description = shifu_draft.description
        shifu_published.avatar_res_bid = shifu_draft.avatar_res_bid
        shifu_published.keywords = shifu_draft.keywords
        shifu_published.llm = shifu_draft.llm
        shifu_published.llm_temperature = shifu_draft.llm_temperature
        shifu_published.price = shifu_draft.price
        shifu_published.updated_user_bid = user_id
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
            outline_item.ask_llm_system_prompt = (
                draft_outline_item.ask_llm_system_prompt
            )
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
        shifu_log_published_struct.struct_bid = generate_id(app)
        shifu_log_published_struct.shifu_bid = shifu_id
        shifu_log_published_struct.struct = history_item.to_json()
        shifu_log_published_struct.created_user_bid = user_id
        shifu_log_published_struct.created_at = now_time
        db.session.add(shifu_log_published_struct)
        db.session.commit()
        thread = threading.Thread(
            target=_run_summary_with_error_handling, args=(app, shifu_id)
        )
        thread.daemon = True  # Ensure thread doesn't prevent app shutdown
        thread.start()
        db.session.commit()
        return get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu_id


def _run_summary_with_error_handling(app, shifu_id):
    """Run shifu summary generation with error handling"""
    try:
        get_shifu_summary(app, shifu_id)
    except Exception as e:
        app.logger.error(f"Failed to generate shifu summary for {shifu_id}: {str(e)}")


def get_shifu_summary(app, shifu_id: str):
    """
    Obtain the shifu summary information
    """
    with app.app_context():
        shifu: ShifuPublishedShifu = (
            ShifuPublishedShifu.query.filter(ShifuPublishedShifu.shifu_bid == shifu_id)
            .order_by(ShifuPublishedShifu.id.desc())
            .first()
        )
        if not shifu:
            app.logger.error(f"get_shifu_summary shifu_id: {shifu_id} not found")
            return

        # Get the prompt word template
        summary_prompt_template = load_prompt_template("summary")
        ask_prompt_template = load_prompt_template("ask")

        # Get course data
        outline_tree, outline_ids, all_blocks, lesson_map = _get_shifu_data(
            app, shifu_id
        )

        # Generate summaries
        outline_summary_map = _generate_summaries(
            app, outline_tree, all_blocks, lesson_map, summary_prompt_template, shifu
        )

        # Generate ask_prompt
        _generate_ask_prompts(
            app,
            outline_tree,
            outline_ids,
            outline_summary_map,
            lesson_map,
            ask_prompt_template,
        )
        shifu.ask_enabled_status = ASK_MODE_ENABLE
        db.session.commit()
        return


def _generate_ask_prompts(
    app,
    shifu_info: ShifuInfoDto,
    outline_ids: list[str],
    outline_summary_map: dict[str, dict],
    outline_item_map: dict[str, ShifuPublishedOutlineItem],
    ask_prompt_template: str,
):
    """
    Generate ask_prompt for each section
    :param app: Flask app
    :param outline_tree: Outline tree
    :param outline_ids: Section ID list
    :param outline_summary_map: Summary mapping
    :param outline_item_map: Outline item mapping
    :param ask_prompt_template: Ask template
    """
    for chapter in shifu_info.outline_items:
        for section in chapter.children:
            # Split outline_summary_map into learned and unlearned parts based on current section ID
            current_section_id = section.bid
            # Find the index of current section in outline_ids
            current_index = outline_ids.index(current_section_id)
            # Split content into learned and unlearned parts
            learned_summaries = []
            unlearned_summaries = []
            for i, section_id in enumerate(outline_ids):
                if section_id in outline_summary_map:
                    if i <= current_index:
                        # Current section and all previous sections (learned)
                        learned_summaries.append(outline_summary_map[section_id])
                    else:
                        # All sections after current section (unlearned)
                        unlearned_summaries.append(outline_summary_map[section_id])

            # Build text for learned content
            learned_text = _build_summary_text(learned_summaries, is_learned=True)

            # Build text for unlearned content
            unlearned_text = _build_summary_text(unlearned_summaries, is_learned=False)

            ask_prompt = _make_ask_prompt(
                app, ask_prompt_template, learned_text, unlearned_text
            )
            outline_item = outline_item_map.get(section.bid)
            if outline_item:
                outline_item.ask_llm_system_prompt = ask_prompt


def _generate_summaries(
    app,
    outline_tree: ShifuInfoDto,
    all_blocks: dict[str, list[ShifuPublishedBlock]],
    outline_item_map: dict[str, ShifuPublishedOutlineItem],
    summary_prompt_template,
    shifu: ShifuPublishedShifu,
) -> dict[str, dict]:
    """
    Generate summaries for all sections
    :param app: Flask app
    :param outline_tree: Outline tree
    :param all_blocks: All block data
    :param outline_item_map: Outline item mapping
    :param summary_prompt_template: Summary template
    :param shifu: Course information
    :return: Summary mapping
    """
    outline_summary_map = {}

    # Get model configuration
    model_name = shifu.llm or shifu.llm
    temperature = shifu.llm_temperature or shifu.ask_llm_temperature or 0.3
    if not model_name:
        model_name = app.config.get("DEFAULT_LLM_MODEL", "")

    for chapter in outline_tree.outline_items:
        for section in chapter.children:
            section_blocks = all_blocks.get(section.bid, [])
            content_blocks = [
                block
                for block in section_blocks
                if block.type == BLOCK_TYPE_CONTENT_VALUE
            ]
            now_lesson_script_prompts = "".join(
                json.loads(block.content)["content"] for block in content_blocks
            )

            final_prompt = summary_prompt_template.format(
                all_script_content=now_lesson_script_prompts
            )

            summary = _get_summary(
                app,
                prompt=final_prompt,
                model_name=model_name,
                temperature=temperature,
            )

            # Update section information
            outline_item = outline_item_map.get(section.bid)
            if outline_item:
                outline_item.summary = summary
                outline_item.ask_enabled_status = ASK_MODE_ENABLE

                # Store summary information
                outline_summary_map[section.bid] = {
                    "chapter_id": chapter.bid,
                    "chapter_name": chapter.title,
                    "section_id": section.bid,
                    "section_name": section.title,
                    "content": summary,
                }

    return outline_summary_map


def _get_shifu_data(app, shifu_id: str) -> tuple[
    ShifuInfoDto,
    list[str],
    dict[str, list[ShifuPublishedBlock]],
    dict[str, ShifuPublishedOutlineItem],
]:
    """
    Get shifu related data
    :param app: Flask app
    :param shifu_id: shifu ID
    :return: (outline_tree, outline_ids, all_blocks, lesson_map)
    """

    outline_ids = []

    shifu_outline_tree = get_shifu_outline_tree(app, shifu_id, is_preview=False)

    q = queue.Queue()
    for item in shifu_outline_tree.outline_items:
        q.put(item)
    while not q.empty():
        item = q.get()
        outline_ids.append(item.bid)
        if item.children:
            for child in item.children:
                q.put(child)

    # Get all section blocks
    all_blocks = _get_all_publish_blocks(app, outline_ids)

    # Get all section data
    outline_items = (
        ShifuPublishedOutlineItem.query.filter(
            ShifuPublishedOutlineItem.outline_item_bid.in_(outline_ids),
            ShifuPublishedOutlineItem.deleted == 0,
        )
        .order_by(ShifuPublishedOutlineItem.id.desc())
        .all()
    )
    outline_item_map = {
        outline_item.outline_item_bid: outline_item for outline_item in outline_items
    }

    return shifu_outline_tree, outline_ids, all_blocks, outline_item_map


def _make_ask_prompt(
    app, ask_prompt: str, learned_text: str, unlearned_text: str
) -> str:
    result = ask_prompt.format(
        learned=("\n" + learned_text) if learned_text else "",
        unlearned=("\n" + unlearned_text) if unlearned_text else "",
        shifu_system_message="{shifu_system_message}",
    )
    return result


def _get_all_publish_blocks(app, outline_ids: list[str]):
    """
    Return {outline_id: [block, ...]}, only contains STATUS_PUBLISH, and each group is sorted by script_index in ascending order
    """
    query = ShifuPublishedBlock.query.filter(
        ShifuPublishedBlock.outline_item_bid.in_(outline_ids),
        ShifuPublishedBlock.deleted == 0,
    )
    blocks: list[ShifuPublishedBlock] = query.all()
    # Group by lesson_id
    result = defaultdict(list)
    for block in blocks:
        result[block.outline_item_bid].append(block)
    # Sort each group by script_index
    for k in result:
        result[k] = sorted(result[k], key=lambda b: b.position)
    return dict(result)


def _get_summary(app, prompt, model_name, user_id=None, temperature=0.8):
    """
    Call the AI model to generate summary
    :param app: Flask app
    :param prompt: Prompt to be summarized
    :param model_name: Model name to use
    :param user_id: Optional, user ID
    :param temperature: Optional, sampling temperature
    :return: Summary text
    """
    # Create langfuse trace/span
    trace = langfuse_client.trace(
        user_id=user_id or "shifu-summary", name="shifu_summary"
    )
    span = trace.span(name="shifu_summary", input=prompt)
    response = invoke_llm(
        app,
        user_id or "shifu-summary",
        span,
        model_name,
        prompt,
        temperature=temperature,
        generation_name="shifu_summary",
    )
    summary = ""
    for chunk in response:
        summary += getattr(chunk, "result", "")
    span.update(output=summary)
    span.end()
    return summary


def _build_summary_text(summaries: list[dict], is_learned: bool) -> str:
    """
    Build a summary text based on whether it's learned or unlearned
    :param summaries: List of summary dictionaries
    :param is_learned: Boolean indicating whether the summary is for learned or unlearned
    :return: Built summary text
    """
    if not summaries:
        return ""

    result_lines = []
    chapter_titles_added = set()

    for summary in summaries:
        chapter_id = summary["chapter_id"]
        chapter_name = summary["chapter_name"]
        section_name = summary["section_name"]
        content = summary["content"]

        # Check if chapter title needs to be added
        if chapter_id not in chapter_titles_added:
            # First time encountering this chapter, add chapter title
            result_lines.append(f"### {chapter_name}")
            chapter_titles_added.add(chapter_id)

        # Add section title and content
        result_lines.append(f"#### {section_name}")
        result_lines.append(content)
        result_lines.append("")  # Add empty line separator

    return "\n".join(result_lines)
