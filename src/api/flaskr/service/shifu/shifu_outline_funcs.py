from flaskr.framework.plugin.plugin_manager import extension
from .dtos import (
    ReorderOutlineItemDto,
    SimpleOutlineDto,
    OutlineDto,
    ShifuOutlineTreeNode,
)
from .const import (
    UNIT_TYPE_VALUES_REVERSE,
    UNIT_TYPE_VALUES,
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_NORMAL,
    UNIT_TYPE_TRIAL,
)
from .models import ShifuDraftOutlineItem
from ...dao import db
from ...util.uuid import generate_id
from ..common.models import raise_error
from datetime import datetime
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from decimal import Decimal
from .adapter import convert_outline_to_reorder_outline_item_dto


# get existing outline items
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to get existing outline items
# usage:
# 1. get existing outline items
# 2. sort outline items by position
def get_existing_outline_items(app, shifu_bid: str) -> list[ShifuDraftOutlineItem]:
    with app.app_context():
        sub_query = (
            db.session.query(db.func.max(ShifuDraftOutlineItem.id))
            .filter(
                ShifuDraftOutlineItem.shifu_bid == shifu_bid,
            )
            .group_by(ShifuDraftOutlineItem.outline_item_bid)
        )
        outline_items = ShifuDraftOutlineItem.query.filter(
            ShifuDraftOutlineItem.id.in_(sub_query),
            ShifuDraftOutlineItem.deleted == 0,
        ).all()

        return sorted(outline_items, key=lambda x: (len(x.position), x.position))


# build outline tree
def build_outline_tree(app, shifu_bid: str) -> list[ShifuOutlineTreeNode]:
    outline_items = get_existing_outline_items(app, shifu_bid)
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
    result = []
    for node in outline_tree:
        result.append(
            SimpleOutlineDto(node.outline_id, node.position, node.outline.title, [])
        )
        if node.children:
            result[-1].children = get_outline_tree_dto(node.children)
    return result


# get outline tree
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to get outline tree
# usage:
# 1. get outline tree
# 2. return outline tree
# 3. it's a plugin function to get outline tree of new shifu draft
@extension("get_outline_tree")
def get_outline_tree(
    result, app, user_id: str, shifu_bid: str
) -> list[SimpleOutlineDto]:
    """get outline tree"""
    app.logger.info(f"get outline tree, user_id: {user_id}, shifu_bid: {shifu_bid}")
    with app.app_context():
        outline_tree = build_outline_tree(app, shifu_bid)
        # return result
        return get_outline_tree_dto(outline_tree)


# create outline
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to create outline
# usage:
# 1. create a new outline
# 2. add a child to the outline
# 3. remove a child from the outline
# 4. it's a plugin function to create outline of new shifu draft and parallel to create outline of old shifu draft
@extension("create_outline")
def create_outline(
    result: SimpleOutlineDto,
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
    """create outline"""
    with app.app_context():
        # generate new outline id
        if result and result.bid:
            outline_bid = result.bid
        else:
            outline_bid = generate_id(app)

        # validate name length
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # check if name conflicts with other outlines
        existing_outline = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.shifu_bid == shifu_id,
                ShifuDraftOutlineItem.title == outline_name,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
            .first()
        )
        if existing_outline:
            raise_error("SHIFU.OUTLINE_NAME_ALREADY_EXISTS")

        # determine position
        existing_items = get_existing_outline_items(app, shifu_id)
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
        new_outline = ShifuDraftOutlineItem(
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
        db.session.commit()

        return SimpleOutlineDto(
            bid=outline_bid, position=new_position, name=outline_name, children=[]
        )


# modify outline
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to modify outline
# usage:
# 1. modify outline
# 2. it's a plugin function to modify outline of new shifu draft
#    and parallel to modify outline of old shifu draft
@extension("modify_outline")
def modify_outline(
    result,
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
    """modify outline"""
    with app.app_context():
        # find existing outline
        existing_outline = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == outline_id,
                ShifuDraftOutlineItem.shifu_bid == shifu_id,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
            .first()
        )

        if not existing_outline:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        if existing_outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_DELETED")

        # validate name length
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # check if name conflicts with other outlines
        name_conflict = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.shifu_bid == shifu_id,
                ShifuDraftOutlineItem.title == outline_name,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .filter(ShifuDraftOutlineItem.outline_item_bid != outline_id)
            .first()
        )

        if name_conflict:
            raise_error("SHIFU.OUTLINE_NAME_ALREADY_EXISTS")

        # check if needs update
        old_check_str = existing_outline.get_str_to_check()
        # create new version
        new_outline: ShifuDraftOutlineItem = existing_outline.clone()
        new_outline.title = outline_name
        new_outline.llm_system_prompt = system_prompt or ""
        new_outline.updated_user_bid = user_id
        new_outline.updated_at = datetime.now()
        # risk check
        new_check_str = new_outline.get_str_to_check()
        if old_check_str != new_check_str:
            check_text_with_risk_control(app, outline_id, user_id, new_check_str)

        # save to database
        if not existing_outline.eq(new_outline):
            db.session.add(new_outline)
            db.session.commit()

        return SimpleOutlineDto(
            bid=outline_id,
            position=existing_outline.position,
            name=outline_name,
            children=[],
        )


# delete outline
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to delete outline
# usage:
# 1. delete outline
# 2. it's a plugin function to delete outline of new shifu draft
#    and parallel to delete outline of old shifu draft
@extension("delete_outline")
def delete_outline(result, app, user_id: str, shifu_id: str, outline_id: str):
    """delete outline"""
    with app.app_context():
        # find the outline to delete
        outline_to_delete = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == outline_id,
                ShifuDraftOutlineItem.shifu_bid == shifu_id,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
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
                ShifuDraftOutlineItem.query.filter(
                    ShifuDraftOutlineItem.outline_item_bid == item_id,
                    ShifuDraftOutlineItem.shifu_bid == shifu_id,
                    ShifuDraftOutlineItem.deleted == 0,
                )
                .order_by(ShifuDraftOutlineItem.id.desc())
                .first()
            )
            if item:
                new_item = item.clone()
                new_item.deleted = 1
                new_item.updated_user_bid = user_id
                new_item.updated_at = datetime.now()
                db.session.add(new_item)

        db.session.commit()
        return True


# reorder outline tree
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to reorder outline tree
# usage:
# 1. reorder outline tree
# 2. it's a plugin function to reorder outline tree of new shifu draft
#    and parallel to reorder outline tree of old shifu draft
@extension("reorder_outline_tree")
def reorder_outline_tree(
    result, app, user_id: str, shifu_id: str, outlines: list[ReorderOutlineItemDto]
):
    """reorder outline tree"""
    with app.app_context():
        app.logger.info(
            f"reorder outline tree, user_id: {user_id}, shifu_id: {shifu_id}"
        )

        # get existing outlines
        existing_items = get_existing_outline_items(app, shifu_id)
        existing_items_map = {item.outline_item_bid: item for item in existing_items}

        # rebuild positions
        def rebuild_positions(
            outline_dtos: list[ReorderOutlineItemDto], parent_position=""
        ):
            for i, outline_dto in enumerate(outline_dtos):
                if outline_dto.bid in existing_items_map:
                    item = existing_items_map[outline_dto.bid]
                    new_position = f"{parent_position}{i + 1:02d}"

                    if item.position != new_position:
                        # create new version
                        new_item = item.clone()
                        new_item.position = new_position
                        new_item.updated_user_bid = user_id
                        new_item.updated_at = datetime.now()
                        db.session.add(new_item)
                        existing_items_map[outline_dto.bid] = new_item

                    # recursively process children
                    if outline_dto.children:
                        rebuild_positions(outline_dto.children, new_position)

        outline_dtos = convert_outline_to_reorder_outline_item_dto(outlines)
        rebuild_positions(outline_dtos)
        db.session.commit()
        return True


# get unit by id
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to get unit by id
# usage:
# 1. get unit by id
# 2. it's a plugin function to get unit by id of new shifu draft
#    and parallel to get unit by id of old shifu draft
@extension("get_unit_by_id")
def get_unit_by_id(result, app, user_id: str, unit_id: str):
    """get unit by id"""
    with app.app_context():
        unit: ShifuDraftOutlineItem = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == unit_id,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
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
            system_prompt=unit.llm_system_prompt,
            is_hidden=is_hidden,
        )


# modify unit
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to modify unit
# usage:
# 1. modify unit
# 2. it's a plugin function to modify unit of new shifu draft
#    and parallel to modify unit of old shifu draft
@extension("modify_unit")
def modify_unit(
    result,
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
    """modify unit"""
    with app.app_context():
        app.logger.info(f"modify unit: {unit_id}, name: {unit_name}")

        # find existing unit
        existing_unit = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == unit_id,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
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
        new_unit: ShifuDraftOutlineItem = existing_unit.clone()

        if unit_name:
            new_unit.title = unit_name
        if unit_system_prompt:
            new_unit.llm_system_prompt = unit_system_prompt
        if unit_is_hidden is True:
            new_unit.hidden = 1
        elif unit_is_hidden is False:
            new_unit.hidden = 0
        if unit_type:
            new_unit.type = UNIT_TYPE_VALUES.get(unit_type, UNIT_TYPE_VALUE_TRIAL)

        new_unit.updated_user_bid = user_id
        new_unit.updated_at = datetime.now()

        # save to database
        if not existing_unit.eq(new_unit):
            # risk check
            new_check_str = new_unit.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, unit_id, user_id, new_check_str)
            existing_unit = new_unit
            db.session.add(new_unit)
            db.session.commit()

        return OutlineDto(
            bid=existing_unit.outline_item_bid,
            position=existing_unit.position,
            name=existing_unit.title,
            description=unit_description or "",
            type=unit_type,
            index=int(existing_unit.position),
            system_prompt=existing_unit.llm_system_prompt,
            is_hidden=unit_is_hidden,
        )


# delete unit
# author: yfge
# date: 2025-07-13
# version: 1.0.0
# description: this function is used to delete unit
# usage:
# 1. delete unit
# 2. it's a plugin function to delete unit of new shifu draft
#    and parallel to delete unit of old shifu draft
@extension("delete_unit")
def delete_unit(result, app, user_id: str, unit_id: str):
    """delete unit"""
    with app.app_context():
        # find the unit to delete
        unit_to_delete = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == unit_id,
                ShifuDraftOutlineItem.deleted == 0,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
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
            item: ShifuDraftOutlineItem = (
                ShifuDraftOutlineItem.query.filter(
                    ShifuDraftOutlineItem.outline_item_bid == item_id,
                )
                .order_by(ShifuDraftOutlineItem.id.desc())
                .first()
            )
            if item:
                new_item = item.clone()
                new_item.deleted = 1
                new_item.updated_user_bid = user_id
                new_item.updated_at = datetime.now()
                db.session.add(new_item)

        db.session.commit()
        return True
