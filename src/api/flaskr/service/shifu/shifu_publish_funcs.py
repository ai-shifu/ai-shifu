"""Shifu publish funcs.

This module contains functions for publishing shifu.

Author: yfge
Date: 2025-08-07
"""

import queue
import threading
from dataclasses import dataclass, field

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.api.llm.tiers import selection_metadata, selection_model
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.dao import db, uow
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.api import (
    is_live_follow_up_model,
    normalize_live_follow_up_course_config,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.consts import (
    ASK_MODE_ENABLE,
    FLOW_ENGINE_DEFAULT,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    get_latest_shifu_draft,
    serialize_ask_provider_config,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_outline_funcs import (
    ShifuOutlineTreeNode,
    assert_outline_items_publishable,
    build_outline_tree_from_items,
    load_existing_outline_items,
)
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuInfoDto,
    get_shifu_outline_tree,
)
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import (
    BlockType,
    MarkdownFlow,
)


def _build_frontend_url(base_url: str, path: str) -> str:
    """Build a frontend URL based on the provided base URL."""
    normalized_base = base_url.rstrip("/") if base_url else ""
    cleaned_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{cleaned_path}" if normalized_base else cleaned_path


def preview_shifu_draft(
    app: object, user_id: str, shifu_id: str, variables: dict, base_url: str
) -> str:
    """Preview shifu draft.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        variables: Variables
        base_url: Base URL to build preview link.

    """
    _ = (user_id, variables)
    with app.app_context():
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("server.shifu.shifuNotFound")

        return _build_frontend_url(base_url, f"/c/{shifu_id}?preview=true")


def publish_shifu_draft(
    app: object,
    user_id: str,
    shifu_id: str,
    base_url: str,
    sync_summary: bool = False,
) -> str:
    """Publish shifu draft will copy all draft data to published data and save history to database and run summary generation in background by default and return published shifu url.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        base_url: Base URL to build published link
        sync_summary: If True, generate summary/ask prompts synchronously in the
            current process (useful for one-off console commands). Default False
            keeps existing async background behavior.

    Returns:
        str: Shifu published URL

    """
    with app_context_scope(app), unit_of_work():
        now_time = now_utc()
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("server.shifu.shifuNotFound")
        outline_items = load_existing_outline_items(shifu_id, include_content=True)
        normalized_provider_config, live_contract_error = (
            normalize_live_follow_up_course_config(
                course_model=selection_model(shifu_draft),
                course_follow_up_model=selection_model(shifu_draft, follow_up=True),
                provider_config=getattr(shifu_draft, "ask_provider_config", "{}"),
            )
        )
        if live_contract_error is not None:
            field = (
                live_contract_error
                if live_contract_error == "model"
                else f"ask_provider_config.{live_contract_error}"
                if live_contract_error in {"provider", "mode"}
                else f"ask_provider_config.config.{live_contract_error}"
            )
            raise_param_error(field)
        PublishedShifu.query.filter_by(shifu_bid=shifu_id).update({"deleted": 1})
        PublishedOutlineItem.query.filter_by(shifu_bid=shifu_id).update({"deleted": 1})
        shifu_published = PublishedShifu()
        shifu_published.shifu_bid = shifu_id
        shifu_published.title = shifu_draft.title
        shifu_published.description = shifu_draft.description
        shifu_published.avatar_res_bid = shifu_draft.avatar_res_bid
        shifu_published.keywords = shifu_draft.keywords
        shifu_published.llm = shifu_draft.llm
        shifu_published.llm_temperature = shifu_draft.llm_temperature
        shifu_published.price = shifu_draft.price
        shifu_published.created_user_bid = shifu_draft.created_user_bid
        shifu_published.updated_user_bid = user_id
        shifu_published.updated_at = now_time
        shifu_published.llm_system_prompt = shifu_draft.llm_system_prompt
        shifu_published.ask_enabled_status = shifu_draft.ask_enabled_status
        # Learners run the published row, so an author who switches the runtime and publishes has
        # to see the switch take effect.
        shifu_published.flow_engine = getattr(
            shifu_draft, "flow_engine", FLOW_ENGINE_DEFAULT
        )
        shifu_published.ask_llm = shifu_draft.ask_llm
        shifu_published.ask_llm_temperature = shifu_draft.ask_llm_temperature
        shifu_published.ask_llm_system_prompt = shifu_draft.ask_llm_system_prompt
        shifu_published.ask_provider_config = serialize_ask_provider_config(
            normalized_provider_config
        )
        # TTS Configuration
        shifu_published.tts_enabled = shifu_draft.tts_enabled
        shifu_published.tts_provider = getattr(shifu_draft, "tts_provider", "") or ""
        shifu_published.tts_model = getattr(shifu_draft, "tts_model", "") or ""
        shifu_published.tts_voice_id = shifu_draft.tts_voice_id
        shifu_published.tts_speed = shifu_draft.tts_speed
        shifu_published.tts_pitch = shifu_draft.tts_pitch
        shifu_published.tts_emotion = shifu_draft.tts_emotion
        shifu_published.default_listen_mode_enabled = getattr(
            shifu_draft, "default_listen_mode_enabled", 0
        )
        # Learner language setting
        shifu_published.use_learner_language = getattr(
            shifu_draft, "use_learner_language", 0
        )
        db.session.add(shifu_published)
        db.session.flush()
        # Block publishing a structurally broken outline instead of silently
        # dropping orphaned/colliding nodes from the published result.
        assert_outline_items_publishable(app, shifu_id, outline_items)
        outline_tree = build_outline_tree_from_items(app, outline_items)

        def publish_outline_item(
            node: ShifuOutlineTreeNode, history_item: HistoryItem
        ) -> None:
            outline_item = PublishedOutlineItem()
            draft_outline_item: DraftOutlineItem = node.outline
            outline_item.shifu_bid = shifu_id
            outline_item.outline_item_bid = draft_outline_item.outline_item_bid
            outline_item.title = draft_outline_item.title
            outline_item.position = draft_outline_item.position
            outline_item.type = draft_outline_item.type
            outline_item.hidden = draft_outline_item.hidden
            outline_item.parent_bid = draft_outline_item.parent_bid
            outline_item.llm_system_prompt = draft_outline_item.llm_system_prompt
            outline_item.ask_enabled_status = draft_outline_item.ask_enabled_status
            outline_item.ask_llm_system_prompt = (
                draft_outline_item.ask_llm_system_prompt
            )
            outline_item.created_user_bid = user_id
            outline_item.updated_user_bid = user_id
            outline_item.updated_at = draft_outline_item.updated_at
            outline_item.prerequisite_item_bids = (
                draft_outline_item.prerequisite_item_bids
            )
            outline_item.content = draft_outline_item.content
            db.session.add(outline_item)
            db.session.flush()
            markdown_flow = MarkdownFlow(
                draft_outline_item.content
            ).set_output_language(get_markdownflow_output_language())
            blocks = markdown_flow.get_all_blocks()
            outline_item_history_item = HistoryItem(
                bid=node.outline_id,
                id=outline_item.id,
                type="outline",
                children=[],
                child_count=len(blocks),
            )
            history_item.children.append(outline_item_history_item)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    publish_outline_item(child, outline_item_history_item)

        history_item = HistoryItem(
            bid=shifu_id, id=shifu_published.id, type="shifu", children=[]
        )
        for node in outline_tree:
            publish_outline_item(node, history_item)

        shifu_log_published_struct = LogPublishedStruct()
        shifu_log_published_struct.struct_bid = generate_id(app)
        shifu_log_published_struct.shifu_bid = shifu_id
        shifu_log_published_struct.struct = history_item.to_json()
        shifu_log_published_struct.created_user_bid = user_id
        shifu_log_published_struct.created_at = now_time
        db.session.add(shifu_log_published_struct)
        parent_shifu_context = get_shifu_context_snapshot()

        def start_summary() -> None:
            if sync_summary:
                _run_summary_with_error_handling(app, shifu_id, parent_shifu_context)
                return
            thread = threading.Thread(
                target=_run_summary_with_error_handling,
                args=(app, shifu_id, parent_shifu_context),
            )
            thread.daemon = True  # Ensure thread doesn't prevent app shutdown
            thread.start()

        # The summary reads the published rows, so it starts only once the
        # publish transaction is durable (and never when it rolls back).
        uow.on_commit(start_summary)
        return _build_frontend_url(base_url, f"/c/{shifu_id}")


def _run_summary_with_error_handling(
    app: object, shifu_id: object, shifu_context_snapshot: object = None
) -> None:
    """Run shifu summary generation with error handling.

    Args:
        app: Flask application instance
        shifu_id: Shifu ID.
        shifu_context_snapshot: Context snapshot to apply in the summary thread.

    """
    try:
        apply_shifu_context_snapshot(shifu_context_snapshot)
        get_shifu_summary(app, shifu_id)
    except Exception as e:
        message = str(e)
        if "cannot schedule new futures after shutdown" in message:
            # Summary generation runs in a fire-and-forget daemon thread. When
            # the worker/process is recycled mid-LLM-call (e.g. a deploy),
            # litellm's fallback tries to schedule on an executor that is already
            # shutting down. This is an expected shutdown race, not a real
            # failure, so log at warning level to avoid paging ops on deploys.
            app.logger.warning(
                "Skipped shifu summary for %s due to worker shutdown race: %s",
                shifu_id,
                message,
            )
        else:
            app.logger.exception(
                "Failed to generate shifu summary for %s: %s",
                shifu_id,
                message,
            )


@dataclass(frozen=True)
class _SummaryModelChoice:
    """Model and temperature the summary and ask generation runs with."""

    model_name: str
    temperature: object
    usage_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _SummaryInputs:
    """Everything the provider calls need, read before the generation starts.

    Only plain values: the generation phase runs with no transaction open, so
    it must not hold ORM instances loaded by the read step.
    """

    model_choice: _SummaryModelChoice
    outline_tree: ShifuInfoDto
    outline_ids: list[str]
    section_contents: dict[str, str]
    summary_prompt_template: object
    ask_prompt_template: str
    # Row identities, not just business bids: a republish during the
    # generation creates NEW rows carrying the same bids, and the generated
    # text describes the rows read here.
    shifu_row_id: int
    outline_row_ids: dict[str, int]


def _resolve_summary_model(app: object, shifu: PublishedShifu) -> _SummaryModelChoice:
    """Pick the model that generates summaries and ask prompts."""
    _ = app
    follow_up = not is_live_follow_up_model(selection_model(shifu, follow_up=True))
    model_name = selection_model(shifu, follow_up=follow_up)
    metadata = selection_metadata(shifu, follow_up=follow_up)
    temperature = (
        shifu.ask_llm_temperature if follow_up else shifu.llm_temperature
    ) or 0.3
    return _SummaryModelChoice(
        model_name=model_name, temperature=temperature, usage_metadata=metadata
    )


def _load_published_shifu(shifu_id: str) -> PublishedShifu | None:
    return (
        PublishedShifu.query.filter(PublishedShifu.shifu_bid == shifu_id)
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _load_summary_inputs(app: object, shifu_id: str) -> _SummaryInputs | None:
    """Read the course data the generation phase needs."""
    shifu = _load_published_shifu(shifu_id)
    if not shifu:
        app.logger.error("get_shifu_summary shifu_id: %s not found", shifu_id)
        return None

    outline_tree, outline_ids, outline_item_map = _get_shifu_data(app, shifu_id)
    return _SummaryInputs(
        model_choice=_resolve_summary_model(app, shifu),
        outline_tree=outline_tree,
        outline_ids=outline_ids,
        section_contents={
            bid: (outline_item.content or "")
            for bid, outline_item in outline_item_map.items()
        },
        summary_prompt_template=load_prompt_template("summary"),
        ask_prompt_template=load_prompt_template("ask"),
        shifu_row_id=int(shifu.id),
        outline_row_ids={
            bid: int(outline_item.id) for bid, outline_item in outline_item_map.items()
        },
    )


def _apply_summary_results(
    app: object,
    shifu_id: str,
    *,
    inputs: _SummaryInputs,
    outline_summary_map: dict[str, dict],
    ask_prompts: dict[str, str],
) -> None:
    """Write the generated ask prompts back to the rows they were read from.

    A republish during the generation retires those rows and creates new ones
    with the same bids. Writing this run's output into the new publication
    would mix two publications, so the apply is skipped entirely instead.
    """
    shifu = _load_published_shifu(shifu_id)
    if not shifu:
        app.logger.error("get_shifu_summary shifu_id: %s not found", shifu_id)
        return
    if int(shifu.id) != inputs.shifu_row_id:
        app.logger.warning(
            "Skipping shifu summary for %s: republished during generation "
            "(read row %s, active row %s)",
            shifu_id,
            inputs.shifu_row_id,
            shifu.id,
        )
        return

    outline_item_map = {
        outline_item.id: outline_item
        for outline_item in PublishedOutlineItem.query.filter(
            PublishedOutlineItem.id.in_(inputs.outline_row_ids.values()),
            PublishedOutlineItem.deleted == 0,
        ).all()
    }
    # Only the ask prompt and the enabled flag are persisted: the summary text
    # is an input to the ask prompts, and `shifu_published_outline_items` has
    # no column for it (the previous `outline_item.summary = ...` assignment
    # set a transient attribute that was dropped with the session).
    for bid in outline_summary_map:
        outline_item = outline_item_map.get(inputs.outline_row_ids.get(bid))
        if outline_item is None:
            continue
        outline_item.ask_enabled_status = ASK_MODE_ENABLE
    for bid, ask_prompt in ask_prompts.items():
        outline_item = outline_item_map.get(inputs.outline_row_ids.get(bid))
        if outline_item is None:
            continue
        outline_item.ask_llm_system_prompt = ask_prompt
    shifu.ask_enabled_status = ASK_MODE_ENABLE


def get_shifu_summary(app: object, shifu_id: str) -> None:
    """Obtain the shifu summary information.

    Args:
        app: Flask application instance
        shifu_id: Shifu ID.

    """
    # Read, generate, apply are three steps with the provider calls between
    # them: nested, neither unit of work would commit and the generation would
    # run inside the caller's transaction after all.
    uow.require_transaction_owner("shifu summary generation")
    with app_context_scope(app):
        # Step 1 - read what the generation needs, then end the transaction.
        with unit_of_work():
            inputs = _load_summary_inputs(app, shifu_id)
        if inputs is None:
            return

        # The provider calls run with NO transaction open: one summary and one
        # ask prompt per section means minutes of LLM round trips, and holding
        # the read transaction across them would pin a pooled connection and a
        # read snapshot for the whole run.
        outline_summary_map = _generate_summaries(
            app,
            inputs.outline_tree,
            inputs.section_contents,
            inputs.summary_prompt_template,
            inputs.model_choice,
        )
        ask_prompts = _generate_ask_prompts(
            app,
            inputs.outline_tree,
            inputs.outline_ids,
            outline_summary_map,
            inputs.ask_prompt_template,
        )

        # Step 2 - apply everything at once, so a failed generation leaves the
        # published course exactly as it was.
        with unit_of_work():
            _apply_summary_results(
                app,
                shifu_id,
                inputs=inputs,
                outline_summary_map=outline_summary_map,
                ask_prompts=ask_prompts,
            )


def _generate_ask_prompts(
    app: object,
    shifu_info: ShifuInfoDto,
    outline_ids: list[str],
    outline_summary_map: dict[str, dict],
    ask_prompt_template: str,
) -> dict[str, str]:
    """Build the ask prompt of each section.

    Pure with respect to the database: it reads no rows and writes none, so it
    can run between the two units of work of ``get_shifu_summary``.

    Args:
        app: Flask application instance
        shifu_info: Shifu info
        outline_ids: Section ID list
        outline_summary_map: Summary mapping
        ask_prompt_template: Ask template
    Returns:
        Mapping of outline item bid to its ask prompt.

    """
    ask_prompts: dict[str, str] = {}
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
            learned_text = _build_summary_text(learned_summaries)

            # Build text for unlearned content
            unlearned_text = _build_summary_text(unlearned_summaries)

            ask_prompts[section.bid] = _make_ask_prompt(
                app, ask_prompt_template, learned_text, unlearned_text
            )
    return ask_prompts


def _generate_summaries(
    app: object,
    outline_tree: ShifuInfoDto,
    section_contents: dict[str, str],
    summary_prompt_template: object,
    model_choice: _SummaryModelChoice,
) -> dict[str, dict]:
    """Generate summaries for all sections.

    Pure with respect to the database: it takes the section content as plain
    strings and returns plain values, so the LLM calls can run between the two
    units of work of ``get_shifu_summary``.

    Args:
        app: Flask application instance
        outline_tree: Outline tree
        section_contents: Outline item bid to its published content
        summary_prompt_template: Summary template
        model_choice: Model and temperature resolved from the course
    Returns:
        Summary mapping.

    """
    outline_summary_map = {}

    for chapter in outline_tree.outline_items:
        for section in chapter.children:
            content = section_contents.get(section.bid)
            if content is None:
                # The tree lists a section the outline query did not return
                # (an inconsistent read of the published rows); there is
                # nothing to write a summary back to.
                continue
            now_lesson_script_prompts = ""
            if content:
                app.logger.info(
                    "outline_item: %s has mdflow content,make summary from mdflow",
                    section.bid,
                )
                mdflow = MarkdownFlow(content).set_output_language(
                    get_markdownflow_output_language()
                )
                blocks = mdflow.get_all_blocks()
                for block in blocks:
                    if block.block_type == BlockType.CONTENT:
                        now_lesson_script_prompts += "\n" + block.content

            final_prompt = summary_prompt_template.format(
                all_script_content=now_lesson_script_prompts
            )

            summary = _get_summary(
                app,
                prompt=final_prompt,
                model_name=model_choice.model_name,
                temperature=model_choice.temperature,
                usage_metadata=model_choice.usage_metadata,
            )
            outline_summary_map[section.bid] = {
                "chapter_id": chapter.bid,
                "chapter_name": chapter.title,
                "section_id": section.bid,
                "section_name": section.title,
                "content": summary,
            }

    return outline_summary_map


def _get_shifu_data(
    app: object, shifu_id: str
) -> tuple[
    ShifuInfoDto,
    list[str],
    dict[str, PublishedOutlineItem],
]:
    """Get shifu related data.

    Args:
        app: Flask application instance
        shifu_id: shifu ID
    Returns:
        (outline_tree, outline_ids, outline_item_map).

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

    # Get all section data
    outline_item_map = _load_outline_item_map(outline_ids)

    return shifu_outline_tree, outline_ids, outline_item_map


def _load_outline_item_map(
    outline_ids: list[str],
) -> dict[str, PublishedOutlineItem]:
    """Map each outline bid to its published row, as the summary flow reads it."""
    outline_items = (
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.outline_item_bid.in_(outline_ids),
            PublishedOutlineItem.deleted == 0,
        )
        .order_by(PublishedOutlineItem.id.desc())
        .all()
    )
    return {
        outline_item.outline_item_bid: outline_item for outline_item in outline_items
    }


def _make_ask_prompt(
    app: object, ask_prompt: str, learned_text: str, unlearned_text: str
) -> str:
    """Make ask prompt.

    Args:
        app: Flask application instance
        ask_prompt: Ask prompt
        learned_text: Learned text
        unlearned_text: Unlearned text
    Returns:
        Ask prompt.

    """
    _ = app
    return ask_prompt.format(
        learned=("\n" + learned_text) if learned_text else "",
        unlearned=("\n" + unlearned_text) if unlearned_text else "",
        # Runtime placeholders: shifu_system_message is filled on every ask;
        # knowledge_rule and knowledge_section are replaced with the rendered
        # knowledge rule/section (or removed entirely) when a retrieval
        # provider is configured.
        shifu_system_message="{shifu_system_message}",
        knowledge_rule="{knowledge_rule}",
        knowledge_section="{knowledge_section}",
    )


def _get_summary(
    app: object,
    prompt: object,
    model_name: object,
    user_id: object = None,
    temperature: object = 0.8,
    usage_metadata: dict | None = None,
) -> str:
    """Call the AI model to generate summary.

    Args:
        app: Flask application instance
        prompt: Prompt to be summarized
        usage_metadata: Selection provenance passed to the usage recorder.
        model_name: Model name to use
        user_id: Optional, user ID
        temperature: Optional, sampling temperature
    Returns:
        Summary text.

    """
    # Create langfuse trace/span
    trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "user_id": user_id or "shifu-summary",
            "input": prompt,
            "name": "shifu_summary",
        },
        root_span_payload={
            "name": "shifu_summary",
            "input": prompt,
        },
    )
    summary = ""
    try:
        response = invoke_llm(
            app,
            user_id or "shifu-summary",
            span,
            model_name,
            prompt,
            temperature=temperature,
            generation_name="shifu_summary",
            usage_metadata=usage_metadata,
            usage_context=UsageContext(
                user_bid=user_id or "shifu-summary",
                shifu_bid="",
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=0,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        for chunk in response:
            summary += getattr(chunk, "result", "")
        return summary
    finally:
        finalize_langfuse_trace(
            trace=trace,
            root_span=span,
            trace_payload={"output": summary},
            root_span_payload={"output": summary},
        )


def _build_summary_text(summaries: list[dict]) -> str:
    """Build a summary text from chapter/section summary entries.

    Args:
        summaries: List of summary dictionaries
    Returns:
        Built summary text.

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
