"""
Shifu outline funcs

This module contains functions for managing shifu outline.

Author: yfge
Date: 2025-08-07
"""

from .dtos import (
    ReorderOutlineItemDto,
    SimpleOutlineDto,
    OutlineDto,
    ShifuOutlineTreeNode,
)
from .consts import (
    UNIT_TYPE_VALUES_REVERSE,
    UNIT_TYPE_VALUES,
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_NORMAL,
    UNIT_TYPE_TRIAL,
)
from .models import DraftOutlineItem
from ...dao import db
from ...util import generate_id
from .adapter import html_2_markdown, markdown_2_html
from ..common.models import raise_error
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from decimal import Decimal
from .adapter import convert_outline_to_reorder_outline_item_dto
from .shifu_history_manager import (
    save_new_outline_history,
    save_outline_tree_history,
    HistoryItem,
    save_outline_history,
    delete_outline_history,
)
from datetime import datetime


def __get_existing_outline_items(shifu_bid: str) -> list[DraftOutlineItem]:
    """
    Get existing outline items
    internal function
    Args:
        shifu_bid: Shifu bid
    Returns:
        list[DraftOutlineItem]: Outline items
    """
    sub_query = (
        db.session.query(db.func.max(DraftOutlineItem.id))
        .filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
        )
        .group_by(DraftOutlineItem.outline_item_bid)
    )
    outline_items = DraftOutlineItem.query.filter(
        DraftOutlineItem.id.in_(sub_query),
        DraftOutlineItem.deleted == 0,
    ).all()

    return sorted(outline_items, key=lambda x: (len(x.position), x.position))


def build_outline_tree(app, shifu_bid: str) -> list[ShifuOutlineTreeNode]:
    """
    Build outline tree
    Args:
        app: Flask application instance
        shifu_bid: Shifu bid
    Returns:
        list[ShifuOutlineTreeNode]: Outline tree
    """
    outline_items = __get_existing_outline_items(shifu_bid)
    sorted_items = sorted(outline_items, key=lambda x: (len(x.position), x.position))
    outline_tree = []

    nodes_map = {}
    for item in sorted_items:
        node = ShifuOutlineTreeNode(item)
        nodes_map[item.position] = node

    # build tree structure
    for position, node in nodes_map.items():
        if len(position) == 2:
            # root node
            outline_tree.append(node)
        else:
            # find parent node
            parent_position = position[:-2]
            if parent_position in nodes_map:
                parent_node = nodes_map[parent_position]
                if node not in parent_node.children:
                    parent_node.add_child(node)
            else:
                app.logger.error(f"Parent node not found for position: {position}")

    return outline_tree


def get_outline_tree_dto(
    outline_tree: list[ShifuOutlineTreeNode],
) -> list[SimpleOutlineDto]:
    """
    Get outline tree dto
    Args:
        outline_tree: Outline tree
    Returns:
        list[SimpleOutlineDto]: Outline tree dto
    """
    result = []
    for node in outline_tree:
        result.append(
            SimpleOutlineDto(node.outline_id, node.position, node.outline.title, [])
        )
        if node.children:
            result[-1].children = get_outline_tree_dto(node.children)
    return result


def get_outline_tree(app, user_id: str, shifu_bid: str) -> list[SimpleOutlineDto]:
    """
    Get outline tree
    build outline tree from outline items
    usage:
    1. get outline tree
    2. return outline tree
    3. it's a plugin function to get outline tree of new shifu draft
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
    Returns:
        list[SimpleOutlineDto]: Outline tree
    """
    app.logger.info(f"get outline tree, user_id: {user_id}, shifu_bid: {shifu_bid}")
    with app.app_context():
        outline_tree = build_outline_tree(app, shifu_bid)
        # return result
        return get_outline_tree_dto(outline_tree)


def create_outline(
    app,
    user_id: str,
    shifu_id: str,
    parent_id: str,
    outline_name: str,
    outline_description: str,
    outline_index: int = 0,
    outline_type: str = UNIT_TYPE_TRIAL,
    system_prompt: str = None,
    is_hidden: bool = False,
):
    """
    Create outline
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        parent_id: Parent ID
        outline_name: Outline name
        outline_description: Outline description
        outline_index: Outline index
        outline_type: Outline type
        system_prompt: System prompt
        is_hidden: Is hidden
    Returns:
        SimpleOutlineDto: Outline dto
    """
    with app.app_context():
        now_time = datetime.now()
        # generate new outline id
        outline_bid = generate_id(app)

        # validate name length
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # determine position
        existing_items = __get_existing_outline_items(shifu_id)
        if parent_id:
            # child outline
            parent_item = next(
                (item for item in existing_items if item.outline_item_bid == parent_id),
                None,
            )
            if not parent_item:
                raise_error("SHIFU.PARENT_OUTLINE_NOT_FOUND")

            # find max index of same level
            siblings = [item for item in existing_items if item.parent_bid == parent_id]
            max_index = (
                max([int(item.position[-2:]) for item in siblings]) if siblings else 0
            )
            new_position = f"{parent_item.position}{max_index + 1:02d}"
        else:
            # top level outline
            root_items = [item for item in existing_items if len(item.position) == 2]
            max_index = (
                max([int(item.position) for item in root_items]) if root_items else 0
            )
            new_position = f"{max_index + 1:02d}"
        type = UNIT_TYPE_VALUES.get(outline_type, UNIT_TYPE_VALUE_TRIAL)

        # create new outline
        new_outline = DraftOutlineItem(
            outline_item_bid=outline_bid,
            shifu_bid=shifu_id,
            title=outline_name,
            parent_bid=parent_id or "",
            position=new_position,
            prerequisite_item_bids="",
            llm="",
            llm_temperature=Decimal("0.3"),
            llm_system_prompt=system_prompt or "",
            ask_enabled_status=5101,  # ASK_MODE_DEFAULT
            ask_llm="",
            ask_llm_temperature=Decimal("0.3"),
            ask_llm_system_prompt="",
            deleted=0,
            created_at=now_time,
            updated_at=now_time,
            created_user_bid=user_id,
            updated_user_bid=user_id,
            type=type,
            hidden=is_hidden,
        )

        # risk check
        check_text_with_risk_control(
            app, outline_bid, user_id, f"{outline_name} {system_prompt or ''}"
        )

        # save to database
        db.session.add(new_outline)
        db.session.flush()
        save_new_outline_history(
            app, user_id, shifu_id, outline_bid, new_outline.id, parent_id, max_index
        )
        db.session.commit()

        return SimpleOutlineDto(
            bid=outline_bid, position=new_position, name=outline_name, children=[]
        )


def modify_outline(
    app,
    user_id: str,
    shifu_id: str,
    outline_id: str,
    outline_name: str,
    outline_description: str,
    outline_index: int = 0,
    outline_type: str = UNIT_TYPE_TRIAL,
    system_prompt: str = None,
    is_hidden: bool = False,
):
    """
    Modify outline
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        outline_id: Outline ID
        outline_name: Outline name
        outline_description: Outline description
        outline_index: Outline index
        outline_type: Outline type
        system_prompt: System prompt
        is_hidden: Is hidden
    Returns:
        SimpleOutlineDto: Outline dto
    """
    with app.app_context():
        # find existing outline
        now_time = datetime.now()
        existing_outline = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_id,
                DraftOutlineItem.shifu_bid == shifu_id,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )

        if not existing_outline:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        if existing_outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_DELETED")

        # validate name length
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # check if needs update
        old_check_str = existing_outline.get_str_to_check()
        # create new version
        new_outline: DraftOutlineItem = existing_outline.clone()
        new_outline.title = outline_name
        new_outline.llm_system_prompt = system_prompt or ""
        new_outline.updated_user_bid = user_id
        new_outline.updated_at = now_time
        # risk check
        new_check_str = new_outline.get_str_to_check()
        if old_check_str != new_check_str:
            check_text_with_risk_control(app, outline_id, user_id, new_check_str)

        # save to database
        if not existing_outline.eq(new_outline):
            db.session.add(new_outline)
            db.session.flush()
            save_outline_history(app, user_id, shifu_id, outline_id, new_outline.id)
            db.session.commit()

        return SimpleOutlineDto(
            bid=outline_id,
            position=existing_outline.position,
            name=outline_name,
            children=[],
        )


def delete_outline(app, user_id: str, shifu_id: str, outline_id: str):
    """
    Delete outline
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        outline_id: Outline ID
    Returns:
        bool: True if deleted, False otherwise
    """
    with app.app_context():
        now_time = datetime.now()
        # find the outline to delete
        outline_to_delete = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_id,
                DraftOutlineItem.shifu_bid == shifu_id,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )

        if not outline_to_delete:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # build outline tree to find all children
        outline_tree = build_outline_tree(app, shifu_id)

        # find the node to delete
        def find_node_by_id(nodes, target_id):
            for node in nodes:
                if node.outline_id == target_id:
                    return node
                if node.children:
                    found = find_node_by_id(node.children, target_id)
                    if found:
                        return found
            return None

        node_to_delete = find_node_by_id(outline_tree, outline_id)
        if not node_to_delete:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # collect all node ids to delete (including children)
        def collect_all_node_ids(node):
            ids = [node.outline_id]
            for child in node.children:
                ids.extend(collect_all_node_ids(child))
            return ids

        ids_to_delete = collect_all_node_ids(node_to_delete)

        # mark all related outlines as deleted
        for item_id in ids_to_delete:
            item = (
                DraftOutlineItem.query.filter(
                    DraftOutlineItem.outline_item_bid == item_id,
                    DraftOutlineItem.shifu_bid == shifu_id,
                    DraftOutlineItem.deleted == 0,
                )
                .order_by(DraftOutlineItem.id.desc())
                .first()
            )
            if item:
                new_item: DraftOutlineItem = item.clone()
                new_item.deleted = 1
                new_item.updated_user_bid = user_id
                new_item.updated_at = now_time
                db.session.add(new_item)
        delete_outline_history(app, user_id, shifu_id, outline_id)
        db.session.commit()
        return True


def reorder_outline_tree(
    app, user_id: str, shifu_id: str, outlines: list[ReorderOutlineItemDto]
):
    """
    Reorder outline tree
    usage:
    1. reorder outline tree

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        outlines: Outline items
    Returns:
        bool: True if reordered, False otherwise
    """
    with app.app_context():
        app.logger.info(
            f"reorder outline tree, user_id: {user_id}, shifu_id: {shifu_id}"
        )
        now_time = datetime.now()

        # get existing outlines
        existing_items = __get_existing_outline_items(shifu_id)
        existing_items_map = {item.outline_item_bid: item for item in existing_items}

        history_infos = []

        # rebuild positions
        def rebuild_positions(
            outline_dtos: list[ReorderOutlineItemDto],
            parent_position="",
            history_infos: list[HistoryItem] = None,
        ):
            for i, outline_dto in enumerate(outline_dtos):
                if outline_dto.bid in existing_items_map:
                    item = existing_items_map[outline_dto.bid]
                    new_position = f"{parent_position}{i + 1:02d}"

                    if item.position != new_position:
                        # create new version
                        new_item: DraftOutlineItem = item.clone()
                        new_item.position = new_position
                        new_item.updated_user_bid = user_id
                        new_item.updated_at = now_time
                        db.session.add(new_item)
                        db.session.flush()
                        history_info = HistoryItem(
                            bid=outline_dto.bid,
                            id=new_item.id,
                            type="outline",
                            children=[],
                        )
                        existing_items_map[outline_dto.bid] = new_item
                    else:
                        history_info = HistoryItem(
                            bid=outline_dto.bid, id=item.id, type="outline", children=[]
                        )

                    history_infos.append(history_info)

                    # recursively process children
                    if outline_dto.children:
                        rebuild_positions(
                            outline_dto.children, new_position, history_info.children
                        )

        outline_dtos = convert_outline_to_reorder_outline_item_dto(outlines)
        rebuild_positions(outline_dtos, history_infos=history_infos)
        save_outline_tree_history(app, user_id, shifu_id, history_infos)
        db.session.commit()
        return True


def get_unit_by_id(app, user_id: str, unit_id: str):
    """
    Get unit by id
    Args:
        app: Flask application instance
        user_id: User ID
        unit_id: Unit ID
    Returns:
        OutlineDto: Outline dto
        None: If unit not found
    """
    with app.app_context():
        unit: DraftOutlineItem = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == unit_id,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )

        if not unit:
            raise_error("SHIFU.UNIT_NOT_FOUND")
        unit_type: str = UNIT_TYPE_VALUES_REVERSE.get(unit.type, UNIT_TYPE_TRIAL)
        is_hidden: bool = True if unit.hidden == 1 else False

        return OutlineDto(
            bid=unit.outline_item_bid,
            position=unit.position,
            name=unit.title,
            description=unit.title,
            index=unit.position,
            type=unit_type,
            system_prompt=markdown_2_html(
                unit.llm_system_prompt if unit.llm_system_prompt is not None else "", []
            ),
            is_hidden=is_hidden,
        )


def modify_unit(
    app,
    user_id: str,
    unit_id: str,
    unit_name: str = None,
    unit_description: str = None,
    unit_index: int = 0,
    unit_system_prompt: str = None,
    unit_is_hidden: bool = False,
    unit_type: str = UNIT_TYPE_NORMAL,
):
    """
    Modify unit
    Args:
        app: Flask application instance
        user_id: User ID
        unit_id: Unit ID
        unit_name: Unit name
        unit_description: Unit description
        unit_index: Unit index
        unit_system_prompt: Unit system prompt
        unit_is_hidden: Unit is hidden
        unit_type: Unit type
    Returns:
        OutlineDto: Outline dto
    """
    with app.app_context():
        app.logger.info(f"modify unit: {unit_id}, name: {unit_name}")
        now_time = datetime.now()
        # find existing unit
        existing_unit = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == unit_id,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )

        if not existing_unit:
            raise_error("SHIFU.UNIT_NOT_FOUND")

        # validate name length
        if unit_name and len(unit_name) > 100:
            raise_error("SHIFU.UNIT_NAME_TOO_LONG")

        # check if needs update
        old_check_str = existing_unit.get_str_to_check()

        # create new version
        new_unit: DraftOutlineItem = existing_unit.clone()

        if unit_name:
            new_unit.title = unit_name
        if unit_system_prompt:
            new_unit.llm_system_prompt = html_2_markdown(unit_system_prompt, [])
        if unit_is_hidden is True:
            new_unit.hidden = 1
        elif unit_is_hidden is False:
            new_unit.hidden = 0
        if unit_type:
            new_unit.type = UNIT_TYPE_VALUES.get(unit_type, UNIT_TYPE_VALUE_TRIAL)

        new_unit.updated_user_bid = user_id
        new_unit.updated_at = now_time

        # save to database
        if not existing_unit.eq(new_unit):
            # risk check
            new_check_str = new_unit.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, unit_id, user_id, new_check_str)
            existing_unit = new_unit
            db.session.add(new_unit)
            db.session.flush()
            save_outline_history(
                app, user_id, existing_unit.shifu_bid, unit_id, new_unit.id
            )
            db.session.commit()

        return OutlineDto(
            bid=existing_unit.outline_item_bid,
            position=existing_unit.position,
            name=existing_unit.title,
            description=unit_description or "",
            type=unit_type,
            index=int(existing_unit.position),
            system_prompt=markdown_2_html(existing_unit.llm_system_prompt or "", []),
            is_hidden=unit_is_hidden,
        )


def delete_unit(app, user_id: str, unit_id: str):
    """
    Delete unit

    Args:
        app: Flask application instance
        user_id: User ID
        unit_id: Unit ID

    Returns:
        bool: True if deleted, False otherwise
    """
    with app.app_context():
        now_time = datetime.now()
        # find the unit to delete
        unit_to_delete = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == unit_id,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )

        if not unit_to_delete:
            raise_error("SHIFU.UNIT_NOT_FOUND")

        # build outline tree to find all children
        outline_tree = build_outline_tree(app, unit_to_delete.shifu_bid)

        # find the node to delete
        def find_node_by_id(nodes: list[ShifuOutlineTreeNode], target_id: str):
            for node in nodes:
                if node.outline_id == target_id:
                    return node
                if node.children:
                    found = find_node_by_id(node.children, target_id)
                    if found:
                        return found
            return None

        node_to_delete = find_node_by_id(outline_tree, unit_id)
        if not node_to_delete:
            raise_error("SHIFU.UNIT_NOT_FOUND")

        # collect all node ids to delete (including children)
        def collect_all_node_ids(node: ShifuOutlineTreeNode):
            ids = [node.outline_id]
            for child in node.children:
                ids.extend(collect_all_node_ids(child))
            return ids

        ids_to_delete = collect_all_node_ids(node_to_delete)

        # mark all related outlines as deleted
        for item_id in ids_to_delete:
            item: DraftOutlineItem = (
                DraftOutlineItem.query.filter(
                    DraftOutlineItem.outline_item_bid == item_id,
                )
                .order_by(DraftOutlineItem.id.desc())
                .first()
            )
            if item:
                new_item: DraftOutlineItem = item.clone()
                new_item.deleted = 1
                new_item.updated_user_bid = user_id
                new_item.updated_at = now_time
                db.session.add(new_item)
        delete_outline_history(app, user_id, unit_to_delete.shifu_bid, unit_id)
        db.session.commit()
        return True
