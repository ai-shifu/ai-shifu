"""Shifu publish funcs.

This module contains functions for publishing shifu.

Author: yfge
Date: 2025-08-07
"""

from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.api import (
    normalize_live_follow_up_course_config,
)
from flaskr.service.shifu.consts import (
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
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc
from markdown_flow import (
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
) -> str:
    """Publish draft content and course settings, preserving version history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        base_url: Base URL to build published link

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
                course_model=shifu_draft.llm,
                course_follow_up_model=shifu_draft.ask_llm,
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
        return _build_frontend_url(base_url, f"/c/{shifu_id}")
