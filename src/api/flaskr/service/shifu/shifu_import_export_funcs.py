import json
import os
from flask import Flask
from werkzeug.datastructures import FileStorage
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from flaskr.dao import db
from flaskr.util import generate_id
from flaskr.service.common.models import raise_error
from flaskr.service.shifu.models import DraftShifu, DraftOutlineItem
from flaskr.service.shifu.shifu_draft_funcs import get_latest_shifu_draft
from flaskr.service.shifu.shifu_struct_manager import get_shifu_struct
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    save_shifu_history,
    save_outline_tree_history,
)
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from markdown_flow import MarkdownFlow


def export_shifu(app: Flask, shifu_id: str, file_path: str) -> str:
    """
    Export a shifu to a JSON file.

    Args:
        app: Flask application instance
        shifu_id: Shifu business identifier
        file_path: Path to save the JSON file

    Returns:
        str: Success message
    """
    with app.app_context():
        # Get shifu draft
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("server.shifu.shifuNotFound")

        # Get shifu structure
        shifu_struct = get_shifu_struct(app, shifu_id, is_preview=True)

        # Get all outline items
        outline_item_ids = []
        q = []
        q.append(shifu_struct)
        while q:
            item = q.pop(0)
            if item.type == "outline":
                outline_item_ids.append(item.id)
            if item.children:
                q.extend(item.children)

        outline_items = []
        if outline_item_ids:
            outline_items = DraftOutlineItem.query.filter(
                DraftOutlineItem.id.in_(outline_item_ids),
                DraftOutlineItem.deleted == 0,
            ).all()

        # Build export data
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "shifu": {
                "shifu_bid": shifu_draft.shifu_bid,
                "title": shifu_draft.title,
                "keywords": shifu_draft.keywords,
                "description": shifu_draft.description,
                "avatar_res_bid": shifu_draft.avatar_res_bid,
                "llm": shifu_draft.llm,
                "llm_temperature": float(shifu_draft.llm_temperature)
                if shifu_draft.llm_temperature
                else 0,
                "llm_system_prompt": shifu_draft.llm_system_prompt,
                "ask_enabled_status": shifu_draft.ask_enabled_status,
                "ask_llm": shifu_draft.ask_llm,
                "ask_llm_temperature": float(shifu_draft.ask_llm_temperature)
                if shifu_draft.ask_llm_temperature
                else 0.0,
                "ask_llm_system_prompt": shifu_draft.ask_llm_system_prompt,
                "price": float(shifu_draft.price) if shifu_draft.price else 0.0,
            },
            "outline_items": [
                {
                    "outline_item_bid": item.outline_item_bid,
                    "title": item.title,
                    "type": item.type,
                    "hidden": item.hidden,
                    "parent_bid": item.parent_bid,
                    "position": item.position,
                    "prerequisite_item_bids": item.prerequisite_item_bids,
                    "llm": item.llm,
                    "llm_temperature": float(item.llm_temperature)
                    if item.llm_temperature
                    else 0,
                    "llm_system_prompt": item.llm_system_prompt,
                    "ask_enabled_status": item.ask_enabled_status,
                    "ask_llm": item.ask_llm,
                    "ask_llm_temperature": float(item.ask_llm_temperature)
                    if item.ask_llm_temperature
                    else 0.0,
                    "ask_llm_system_prompt": item.ask_llm_system_prompt,
                    "content": item.content,
                }
                for item in outline_items
            ],
            "structure": json.loads(shifu_struct.to_json()),
        }

        # Write to file
        os.makedirs(
            os.path.dirname(file_path) if os.path.dirname(file_path) else ".",
            exist_ok=True,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        return "success"


def import_shifu(
    app: Flask,
    shifu_id: Optional[str],
    file: FileStorage,
    user_id: str,
    commit: bool = True,
) -> str:
    """
    Import a shifu from a JSON file.

    Args:
        app: Flask application instance
        shifu_id: Optional shifu business identifier. If provided and exists, will update existing shifu.
                  If not provided or doesn't exist, will create a new shifu.
        file: FileStorage object containing the JSON file
        user_id: User ID for creating/updating the shifu

    Returns:
        str: The shifu_bid of the imported shifu
    """
    with app.app_context():
        # Read JSON file
        try:
            file_content = file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode("utf-8")
            import_data = json.loads(file_content)
        except Exception as e:
            app.logger.error(f"Failed to parse JSON file: {e}")
            raise_error("server.shifu.importFileInvalid")

        # Validate import data
        if "shifu" not in import_data or "outline_items" not in import_data:
            raise_error("server.shifu.importFileInvalid")

        shifu_data = import_data["shifu"]
        outline_items_data = import_data["outline_items"]
        structure_data = import_data.get("structure")

        now_time = datetime.now()

        # Determine shifu_bid
        shifu_bid = shifu_id
        if shifu_bid:
            # Check if shifu exists
            existing_shifu = get_latest_shifu_draft(shifu_bid)
            if existing_shifu:
                # Update existing shifu
                new_shifu = existing_shifu.clone()
                new_shifu.title = shifu_data["title"]
                new_shifu.keywords = shifu_data.get("keywords", "")
                new_shifu.description = shifu_data.get("description", "")
                new_shifu.avatar_res_bid = shifu_data.get("avatar_res_bid", "")
                new_shifu.llm = shifu_data.get("llm", "")
                new_shifu.llm_temperature = Decimal(
                    str(shifu_data.get("llm_temperature", 0))
                )
                new_shifu.llm_system_prompt = shifu_data.get("llm_system_prompt", "")
                new_shifu.ask_enabled_status = shifu_data.get(
                    "ask_enabled_status", 5101
                )
                new_shifu.ask_llm = shifu_data.get("ask_llm", "")
                new_shifu.ask_llm_temperature = Decimal(
                    str(shifu_data.get("ask_llm_temperature", 0.0))
                )
                new_shifu.ask_llm_system_prompt = shifu_data.get(
                    "ask_llm_system_prompt", ""
                )
                new_shifu.price = Decimal(str(shifu_data.get("price", 0.0)))
                new_shifu.updated_user_bid = user_id
                new_shifu.updated_at = now_time

                # Risk check
                check_content = (
                    f"{new_shifu.title} {new_shifu.keywords} {new_shifu.description}"
                )
                check_text_with_risk_control(app, shifu_bid, user_id, check_content)

                db.session.add(new_shifu)
                db.session.flush()
                save_shifu_history(app, user_id, shifu_bid, new_shifu.id)

                # Delete old outline items
                DraftOutlineItem.query.filter(
                    DraftOutlineItem.shifu_bid == shifu_bid,
                    DraftOutlineItem.deleted == 0,
                ).update({"deleted": 1})
            else:
                # Create new shifu with provided bid
                new_shifu = DraftShifu(
                    shifu_bid=shifu_bid,
                    title=shifu_data["title"],
                    keywords=shifu_data.get("keywords", ""),
                    description=shifu_data.get("description", ""),
                    avatar_res_bid=shifu_data.get("avatar_res_bid", ""),
                    llm=shifu_data.get("llm", ""),
                    llm_temperature=Decimal(str(shifu_data.get("llm_temperature", 0))),
                    llm_system_prompt=shifu_data.get("llm_system_prompt", ""),
                    ask_enabled_status=shifu_data.get("ask_enabled_status", 5101),
                    ask_llm=shifu_data.get("ask_llm", ""),
                    ask_llm_temperature=Decimal(
                        str(shifu_data.get("ask_llm_temperature", 0.0))
                    ),
                    ask_llm_system_prompt=shifu_data.get("ask_llm_system_prompt", ""),
                    price=Decimal(str(shifu_data.get("price", 0.0))),
                    deleted=0,
                    created_user_bid=user_id,
                    created_at=now_time,
                    updated_user_bid=user_id,
                    updated_at=now_time,
                )

                # Risk check
                check_content = (
                    f"{new_shifu.title} {new_shifu.keywords} {new_shifu.description}"
                )
                check_text_with_risk_control(app, shifu_bid, user_id, check_content)

                db.session.add(new_shifu)
                db.session.flush()
                save_shifu_history(app, user_id, shifu_bid, new_shifu.id)
        else:
            # Create new shifu with generated bid
            shifu_bid = generate_id(app)
            new_shifu = DraftShifu(
                shifu_bid=shifu_bid,
                title=shifu_data["title"],
                keywords=shifu_data.get("keywords", ""),
                description=shifu_data.get("description", ""),
                avatar_res_bid=shifu_data.get("avatar_res_bid", ""),
                llm=shifu_data.get("llm", ""),
                llm_temperature=Decimal(str(shifu_data.get("llm_temperature", 0))),
                llm_system_prompt=shifu_data.get("llm_system_prompt", ""),
                ask_enabled_status=shifu_data.get("ask_enabled_status", 5101),
                ask_llm=shifu_data.get("ask_llm", ""),
                ask_llm_temperature=Decimal(
                    str(shifu_data.get("ask_llm_temperature", 0.0))
                ),
                ask_llm_system_prompt=shifu_data.get("ask_llm_system_prompt", ""),
                price=Decimal(str(shifu_data.get("price", 0.0))),
                deleted=0,
                created_user_bid=user_id,
                created_at=now_time,
                updated_user_bid=user_id,
                updated_at=now_time,
            )

            # Risk check
            check_content = (
                f"{new_shifu.title} {new_shifu.keywords} {new_shifu.description}"
            )
            check_text_with_risk_control(app, shifu_bid, user_id, check_content)

            db.session.add(new_shifu)
            db.session.flush()
            save_shifu_history(app, user_id, shifu_bid, new_shifu.id)

        # Create mapping from old outline_item_bid to new outline_item_bid
        old_to_new_bid_map: Dict[str, str] = {}

        # Create a map of old_bid -> outline_item_data
        outline_items_by_old_bid: Dict[str, dict] = {
            item["outline_item_bid"]: item for item in outline_items_data
        }

        # Create all outline items first (without parent_bid, will update later)
        created_items: Dict[str, DraftOutlineItem] = {}

        for item_data in outline_items_data:
            old_bid = item_data["outline_item_bid"]
            new_bid = generate_id(app)
            old_to_new_bid_map[old_bid] = new_bid

            new_outline = DraftOutlineItem(
                outline_item_bid=new_bid,
                shifu_bid=shifu_bid,
                title=item_data.get("title", ""),
                type=item_data.get("type", 401),
                hidden=item_data.get("hidden", 0),
                parent_bid="",  # Will update after all items are created
                position=item_data.get("position", ""),
                prerequisite_item_bids="",  # Will update after all items are created
                llm=item_data.get("llm", ""),
                llm_temperature=Decimal(str(item_data.get("llm_temperature", 0))),
                llm_system_prompt=item_data.get("llm_system_prompt", ""),
                ask_enabled_status=item_data.get("ask_enabled_status", 5101),
                ask_llm=item_data.get("ask_llm", ""),
                ask_llm_temperature=Decimal(
                    str(item_data.get("ask_llm_temperature", 0.0))
                ),
                ask_llm_system_prompt=item_data.get("ask_llm_system_prompt", ""),
                content=item_data.get("content", ""),
                deleted=0,
                created_at=now_time,
                updated_at=now_time,
                created_user_bid=user_id,
                updated_user_bid=user_id,
            )

            # Risk check
            check_text_with_risk_control(
                app,
                new_bid,
                user_id,
                f"{new_outline.title} {new_outline.llm_system_prompt}",
            )

            db.session.add(new_outline)
            db.session.flush()
            created_items[old_bid] = new_outline

        # Update parent_bid and prerequisite_item_bids for all created items
        for old_bid, new_outline in created_items.items():
            item_data = outline_items_by_old_bid[old_bid]

            # Update parent_bid
            parent_old_bid = item_data.get("parent_bid", "")
            if parent_old_bid:
                parent_new_bid = old_to_new_bid_map.get(parent_old_bid, "")
                if parent_new_bid:
                    new_outline.parent_bid = parent_new_bid

            # Update prerequisite_item_bids
            old_prerequisite_bids = item_data.get("prerequisite_item_bids", "")
            if old_prerequisite_bids:
                old_prerequisite_list = [
                    bid.strip()
                    for bid in old_prerequisite_bids.split(",")
                    if bid.strip()
                ]
                new_prerequisite_list = [
                    old_to_new_bid_map.get(old_bid, "")
                    for old_bid in old_prerequisite_list
                    if old_bid in old_to_new_bid_map
                ]
                new_outline.prerequisite_item_bids = ",".join(new_prerequisite_list)

        # Rebuild structure
        if structure_data:

            def rebuild_structure(struct_item: dict) -> HistoryItem:
                old_bid = struct_item.get("bid", "")
                new_bid = old_to_new_bid_map.get(old_bid, old_bid)
                item_type = struct_item.get("type", "")

                child_count = 0
                # For shifu, use the new shifu_bid
                if item_type == "shifu":
                    new_bid = shifu_bid
                    item_id = new_shifu.id
                elif item_type == "outline":
                    if old_bid in created_items:
                        item_id = created_items[old_bid].id
                        mdflow = MarkdownFlow(created_items[old_bid].content)
                        block_list = mdflow.get_all_blocks()
                        child_count = len(block_list)
                    else:
                        return None
                else:
                    # For blocks, keep the structure but we don't recreate them here
                    item_id = struct_item.get("id", 0)

                children = []
                for child_struct in struct_item.get("children", []):
                    child_item = rebuild_structure(child_struct)
                    if child_item:
                        children.append(child_item)

                return HistoryItem(
                    bid=new_bid,
                    id=item_id,
                    type=item_type,
                    children=children,
                    child_count=child_count,
                )

            new_structure = rebuild_structure(structure_data)
            if new_structure:
                # Save outline tree history
                outline_tree = new_structure.children if new_structure.children else []
                save_outline_tree_history(app, user_id, shifu_bid, outline_tree)

        if commit:
            db.session.commit()
        else:
            db.session.flush()

        return shifu_bid
