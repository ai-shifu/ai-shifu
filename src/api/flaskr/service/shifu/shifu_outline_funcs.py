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
    UNIT_TYPE_TRIAL,
    UNIT_TYPE_GUEST,
)
from .models import DraftOutlineItem, DraftShifu
from ...dao import db
from ...util import generate_id
from ..common.models import raise_error, raise_param_error
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from decimal import Decimal
from .shifu_history_manager import (
    save_new_outline_history,
    save_outline_tree_history,
    HistoryItem,
    save_outline_history,
    delete_outline_history,
)
from .shifu_mdflow_funcs import cleanup_outline_history_versions
from flaskr.util.datetime import now_utc
from markdown_flow import MarkdownFlow

from flaskr.common.i18n_utils import get_markdownflow_output_language


def convert_outline_to_reorder_outline_item_dto(
    json_array: list[dict],
) -> ReorderOutlineItemDto:
    """
    convert outline to reorder outline item dto
    Args:
        json_array: The json array to convert
    Returns:
        The reorder outline item dto
    """
    if not isinstance(json_array, list):
        raise_param_error("outlines")

    result = []
    for item in json_array:
        if not isinstance(item, dict):
            raise_param_error("outlines")
        result.append(
            ReorderOutlineItemDto(
                bid=item.get("bid"),
                children=convert_outline_to_reorder_outline_item_dto(
                    item.get("children") or []
                ),
            )
        )
    return result


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
        # Only positions two chars deeper than a root have a real parent to
        # look up. Requiring len > 2 (rather than the previous "!= 2") is what
        # keeps a malformed position such as "" or a single char from ever
        # looking up itself as its own parent: "".removesuffix path,
        # ""[:-2] == "" would be found in nodes_map and the node would be
        # add_child()'d onto itself, producing a self-cycle that later blows up
        # get_outline_tree_dto with RecursionError. Such degenerate positions
        # now fall through to the orphan branch and are lifted to the root.
        parent_position = position[:-2]
        if len(position) == 2:
            # root node
            outline_tree.append(node)
        elif len(position) > 2 and parent_position in nodes_map:
            parent_node = nodes_map[parent_position]
            if node not in parent_node.children:
                parent_node.add_child(node)
        else:
            # Orphan / malformed node: either its parent position is missing
            # (e.g. the parent unit was deleted without cascading to this child)
            # or the position itself is degenerate (empty / odd length). Instead
            # of silently dropping the node and its whole subtree, self-heal by
            # attaching it at the root level and log it. This keeps the node
            # visible in the editor (so a creator can delete or re-parent it)
            # and prevents publish from losing data. Iteration order is by
            # position length, so a well-formed orphan is already in nodes_map
            # before its own children are processed; they will still attach to
            # it normally.
            app.logger.warning(
                f"Parent node not found for position: {position}, "
                f"attaching orphan '{node.outline_id}' at root level"
            )
            outline_tree.append(node)

    return outline_tree


def assert_outline_tree_publishable(app, shifu_bid: str) -> None:
    """
    Validate that the outline structure can be published without silent data
    loss. Orphaned nodes are tolerated (build_outline_tree self-heals them by
    lifting them to the root level), but two live items sharing the same
    `position` cannot be reconciled: build_outline_tree keys nodes by position,
    so one would overwrite the other and disappear from the published result.
    Block publishing in that case with a clear, actionable error instead of
    quietly shipping a broken course.

    Args:
        app: Flask application instance
        shifu_bid: Shifu bid

    Raises:
        AppException: server.shifu.outlineStructureBroken when positions collide
    """
    existing_items = __get_existing_outline_items(shifu_bid)
    positions: dict[str, list[str]] = {}
    for item in existing_items:
        positions.setdefault(item.position, []).append(item.outline_item_bid)

    collisions = {pos: bids for pos, bids in positions.items() if len(bids) > 1}
    if collisions:
        app.logger.error(
            f"Outline position collisions for shifu {shifu_bid}: {collisions}"
        )
        raise_error("server.shifu.outlineStructureBroken")


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
        node_outline = node.outline
        outline_title = node_outline.title if node_outline else ""
        outline_type = (
            UNIT_TYPE_VALUES_REVERSE.get(node_outline.type, UNIT_TYPE_TRIAL)
            if node_outline
            else UNIT_TYPE_TRIAL
        )
        is_hidden = bool(node_outline.hidden) if node_outline else False
        result.append(
            SimpleOutlineDto(
                node.outline_id,
                node.position,
                outline_title,
                [],
                outline_type,
                is_hidden,
            )
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


def __lock_shifu_for_outline_write(shifu_id: str) -> None:
    """Serialize concurrent outline structural writes for a single shifu.

    A new outline's ``position`` is allocated by reading the current siblings and
    taking ``max(position) + 1``. Without a lock, concurrent create requests read
    the same snapshot and allocate the *same* position, producing colliding
    positions that later block publishing (``assert_outline_tree_publishable``).

    Take a row lock on the shifu's latest draft row so position allocation is
    serialized per shifu. ``DraftShifu`` rows are not written by outline creation,
    so the latest row is a stable lock target that concurrent creators contend on
    (unlike the append-only outline/struct-log rows, whose "latest" identity
    shifts per write). ``FOR UPDATE`` is a no-op on SQLite (unit tests) and
    effective on MySQL (production).
    """
    (
        DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_id)
        .order_by(DraftShifu.id.desc())
        .with_for_update()
        .first()
    )


def __normalize_outline_name(outline_name: str) -> str:
    """Validate and normalize an outline name (local, no I/O)."""
    if not isinstance(outline_name, str) or not outline_name.strip():
        raise_param_error("name")
    outline_name = outline_name.strip()
    if len(outline_name) > 100:
        raise_error("server.shifu.outlineNameTooLong")
    return outline_name


def __insert_outline_locked(
    app,
    user_id: str,
    shifu_id: str,
    parent_id: str,
    outline_name: str,
    outline_type: str,
    system_prompt: str,
    is_hidden: bool,
    now_time,
    outline_bid: str,
    persist_history: bool = True,
) -> SimpleOutlineDto:
    """Insert one outline row, allocating its position from current siblings.

    Caller must already hold the app context, the per-shifu write lock (see
    ``__lock_shifu_for_outline_write``), and own the surrounding transaction: this
    helper flushes but does not commit, so a batch of inserts reads each other's
    freshly flushed positions and stays collision-free within one transaction.

    ``outline_bid`` is generated by the caller and the name is already normalized
    and risk-checked *before* the lock is taken, so this helper performs no id
    generation and no external network I/O while the lock is held.
    """
    # A brand-new outline has no current value to preserve, so a None
    # type/is_hidden (caller omitted it) falls back to a concrete default.
    if outline_type is None:
        outline_type = UNIT_TYPE_GUEST
    if is_hidden is None:
        is_hidden = False

    outline_name = __normalize_outline_name(outline_name)

    # determine position
    existing_items = __get_existing_outline_items(shifu_id)
    if parent_id:
        # child outline
        parent_item = next(
            (item for item in existing_items if item.outline_item_bid == parent_id),
            None,
        )
        if not parent_item:
            raise_error("server.shifu.parentOutlineNotFound")

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
    type_value = UNIT_TYPE_VALUES.get(outline_type, UNIT_TYPE_VALUE_TRIAL)
    type_label = UNIT_TYPE_VALUES_REVERSE.get(
        type_value, outline_type or UNIT_TYPE_TRIAL
    )

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
        type=type_value,
        hidden=is_hidden,
    )

    # save to database (flush only; the caller owns the commit)
    db.session.add(new_outline)
    db.session.flush()
    if persist_history:
        save_new_outline_history(
            app, user_id, shifu_id, outline_bid, new_outline.id, parent_id, max_index
        )

    return SimpleOutlineDto(
        bid=outline_bid,
        position=new_position,
        name=outline_name,
        children=[],
        type=type_label,
        is_hidden=is_hidden,
    )


def create_outline(
    app,
    user_id: str,
    shifu_id: str,
    parent_id: str,
    outline_name: str,
    outline_type: str = UNIT_TYPE_GUEST,
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
        outline_type: Outline type
        system_prompt: System prompt
        is_hidden: Is hidden
    Returns:
        SimpleOutlineDto: Outline dto
    """
    with app.app_context():
        now_time = now_utc()
        # Generate the id and run the external risk check BEFORE taking the
        # per-shifu lock, so no network I/O happens while the lock is held.
        outline_name = __normalize_outline_name(outline_name)
        outline_bid = generate_id(app)
        check_text_with_risk_control(
            app, outline_bid, user_id, f"{outline_name} {system_prompt or ''}"
        )
        __lock_shifu_for_outline_write(shifu_id)
        dto = __insert_outline_locked(
            app,
            user_id,
            shifu_id,
            parent_id,
            outline_name,
            outline_type,
            system_prompt,
            is_hidden,
            now_time,
            outline_bid,
        )
        db.session.commit()
        return dto


def create_default_outlines_for_new_shifu(
    app,
    user_id: str,
    shifu_id: str,
    chapter_name: str,
    lesson_name: str,
    now_time,
    shifu_db_id: int | None = None,
) -> tuple[SimpleOutlineDto, SimpleOutlineDto]:
    """Create the default chapter/lesson pair for a brand-new shifu draft.

    This helper intentionally skips both external risk checks and the per-shifu
    write lock. The names are system-generated, and a brand-new shifu has no
    concurrent outline writes yet, so we can build the initial structure inside
    the caller's existing transaction without opening a nested outline flow.
    """

    normalized_chapter_name = __normalize_outline_name(chapter_name)
    normalized_lesson_name = __normalize_outline_name(lesson_name)
    chapter_bid = generate_id(app)
    lesson_bid = generate_id(app)

    chapter = __insert_outline_locked(
        app,
        user_id,
        shifu_id,
        "",
        normalized_chapter_name,
        UNIT_TYPE_GUEST,
        None,
        False,
        now_time,
        chapter_bid,
        persist_history=False,
    )
    lesson = __insert_outline_locked(
        app,
        user_id,
        shifu_id,
        chapter_bid,
        normalized_lesson_name,
        UNIT_TYPE_GUEST,
        None,
        False,
        now_time,
        lesson_bid,
        persist_history=False,
    )
    outline_items = __get_existing_outline_items(shifu_id)
    history_tree = _build_outline_history_tree(outline_items)
    save_outline_tree_history(
        app=app,
        user_id=user_id,
        shifu_bid=shifu_id,
        outline_tree=history_tree,
        shifu_id=shifu_db_id,
    )
    return chapter, lesson


def _build_outline_history_tree(
    outlines: list[DraftOutlineItem],
) -> list[HistoryItem]:
    outline_children_map: dict[str, list[DraftOutlineItem]] = {}
    for outline in outlines:
        parent_bid = str(outline.parent_bid or "").strip()
        outline_children_map.setdefault(parent_bid, []).append(outline)

    output_lang = get_markdownflow_output_language()

    def _count_blocks(content: str) -> int:
        if not content:
            return 0
        mdflow = MarkdownFlow(content).set_output_language(output_lang)
        return len(mdflow.get_all_blocks())

    def _build(parent_bid: str) -> list[HistoryItem]:
        children = outline_children_map.get(parent_bid, [])
        children.sort(key=lambda item: (item.position or "", item.id))
        return [
            HistoryItem(
                bid=str(child.outline_item_bid or "").strip(),
                id=int(child.id),
                type="outline",
                children=_build(str(child.outline_item_bid or "").strip()),
                child_count=_count_blocks(child.content or ""),
            )
            for child in children
        ]

    return _build("")


def create_outlines_batch(
    app,
    user_id: str,
    shifu_id: str,
    outlines: list,
    parent_id: str = "",
):
    """Create multiple outlines atomically with correct sequential positions.

    Every row is inserted under a single per-shifu lock inside one transaction,
    so a batch of siblings can never collide on the same position. This is the
    safe alternative to issuing N concurrent single-create requests, which race
    on position allocation and can leave a shifu unpublishable.

    Args:
        outlines: nested nodes, each a dict with keys ``name`` (required),
            ``type``, ``system_prompt``, ``is_hidden``, and ``children`` (a list
            of the same shape).
        parent_id: parent outline bid the whole batch is nested under ("" = root).

    Returns:
        list[SimpleOutlineDto]: created nodes, children populated recursively.
    """
    if not isinstance(outlines, list) or not outlines:
        raise_param_error("outlines")

    with app.app_context():
        now_time = now_utc()

        # Pre-pass OUTSIDE the lock: validate each node, generate its id, and run
        # the external risk check. Doing all network I/O before acquiring the
        # per-shifu lock keeps the locked transaction free of external calls
        # (no connection-pool exhaustion, minimal lock hold time).
        def _prepare(nodes: list) -> list:
            prepared = []
            for node in nodes:
                if not isinstance(node, dict):
                    raise_param_error("outlines")
                name = __normalize_outline_name(node.get("name"))
                system_prompt = node.get("system_prompt")
                outline_bid = generate_id(app)
                check_text_with_risk_control(
                    app, outline_bid, user_id, f"{name} {system_prompt or ''}"
                )
                prepared.append(
                    {
                        "bid": outline_bid,
                        "name": name,
                        "type": node.get("type"),
                        "system_prompt": system_prompt,
                        "is_hidden": node.get("is_hidden"),
                        "children": _prepare(node.get("children") or []),
                    }
                )
            return prepared

        prepared = _prepare(outlines)

        __lock_shifu_for_outline_write(shifu_id)

        def _insert(nodes: list, node_parent_id: str) -> list:
            created = []
            for node in nodes:
                dto = __insert_outline_locked(
                    app,
                    user_id,
                    shifu_id,
                    node_parent_id,
                    node["name"],
                    node["type"],
                    node["system_prompt"],
                    node["is_hidden"],
                    now_time,
                    node["bid"],
                )
                if node["children"]:
                    dto.children = _insert(node["children"], dto.bid)
                created.append(dto)
            return created

        results = _insert(prepared, parent_id or "")
        db.session.commit()
        return results


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
        now_time = now_utc()
        __lock_shifu_for_outline_write(shifu_id)

        # get existing outlines
        existing_items = __get_existing_outline_items(shifu_id)
        existing_items_map = {item.outline_item_bid: item for item in existing_items}
        changed_outline_bids = set()

        history_infos = []

        # rebuild positions
        def rebuild_positions(
            outline_dtos: list[ReorderOutlineItemDto],
            parent_position="",
            parent_bid="",
            history_infos: list[HistoryItem] | None = None,
        ):
            if history_infos is None:
                history_infos = []
            for i, outline_dto in enumerate(outline_dtos):
                if outline_dto.bid in existing_items_map:
                    item = existing_items_map[outline_dto.bid]
                    new_position = f"{parent_position}{i + 1:02d}"
                    new_parent_bid = parent_bid or ""
                    if (
                        item.position != new_position
                        or (item.parent_bid or "") != new_parent_bid
                    ):
                        # create new version
                        new_item: DraftOutlineItem = item.clone()
                        new_item.position = new_position
                        new_item.parent_bid = new_parent_bid
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
                        changed_outline_bids.add(outline_dto.bid)
                        existing_items_map[outline_dto.bid] = new_item
                    else:
                        history_info = HistoryItem(
                            bid=outline_dto.bid, id=item.id, type="outline", children=[]
                        )
                    if history_info.child_count == 0 and bool(item.content):
                        mdflow = MarkdownFlow(item.content).set_output_language(
                            get_markdownflow_output_language()
                        )
                        block_list = mdflow.get_all_blocks()
                        history_info.child_count = len(block_list)

                    history_infos.append(history_info)

                    # recursively process children
                    if outline_dto.children:
                        rebuild_positions(
                            outline_dto.children,
                            new_position,
                            outline_dto.bid,
                            history_info.children,
                        )

        outline_dtos = convert_outline_to_reorder_outline_item_dto(outlines)
        rebuild_positions(outline_dtos, history_infos=history_infos)
        for outline_bid in changed_outline_bids:
            cleanup_outline_history_versions(app, shifu_id, outline_bid)
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
            raise_error("server.shifu.unitNotFound")
        unit_type: str = UNIT_TYPE_VALUES_REVERSE.get(unit.type, UNIT_TYPE_TRIAL)
        is_hidden: bool = True if unit.hidden == 1 else False

        return OutlineDto(
            bid=unit.outline_item_bid,
            position=unit.position,
            name=unit.title,
            description=unit.title,
            index=unit.position,
            type=unit_type,
            system_prompt=unit.llm_system_prompt
            if unit.llm_system_prompt is not None
            else "",
            is_hidden=is_hidden,
        )


def modify_unit(
    app,
    user_id: str,
    unit_id: str,
    unit_name: str = None,
    unit_description: str = None,
    unit_system_prompt: str = None,
    unit_is_hidden: bool | None = None,
    unit_type: str | None = None,
):
    """
    Modify unit
    Args:
        app: Flask application instance
        user_id: User ID
        unit_id: Unit ID
        unit_name: Unit name
        unit_description: Unit description
        unit_system_prompt: Unit system prompt
        unit_is_hidden: Unit is hidden
        unit_type: Unit type
    Returns:
        OutlineDto: Outline dto
    """
    with app.app_context():
        app.logger.info(f"modify unit: {unit_id}, name: {unit_name}")
        now_time = now_utc()
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
            raise_error("server.shifu.unitNotFound")

        # validate name length
        if unit_name and len(unit_name) > 100:
            raise_error("server.shifu.unitNameTooLong")

        # check if needs update
        old_check_str = existing_unit.get_str_to_check()

        # create new version
        new_unit: DraftOutlineItem = existing_unit.clone()

        # PATCH semantics: only change a field the caller provided (non-None);
        # an omitted type/is_hidden must keep the unit's current value rather
        # than reset it (this is what made a plain rename wipe the permission).
        if unit_name is not None:
            new_unit.title = unit_name
        if unit_system_prompt is not None:
            new_unit.llm_system_prompt = unit_system_prompt
        if unit_is_hidden is not None:
            new_unit.hidden = 1 if unit_is_hidden else 0
        if unit_type is not None:
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
            cleanup_outline_history_versions(app, existing_unit.shifu_bid, unit_id)
            db.session.commit()

        return OutlineDto(
            bid=existing_unit.outline_item_bid,
            position=existing_unit.position,
            name=existing_unit.title,
            description=unit_description or "",
            # Reflect the actually-stored values, not the (possibly None) inputs.
            type=UNIT_TYPE_VALUES_REVERSE.get(existing_unit.type, UNIT_TYPE_GUEST),
            index=int(existing_unit.position),
            system_prompt=existing_unit.llm_system_prompt or "",
            is_hidden=bool(existing_unit.hidden),
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
        now_time = now_utc()
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
            raise_error("server.shifu.unitNotFound")

        # Collect the unit itself plus every live descendant.
        #
        # We deliberately walk parent_bid instead of building the position
        # tree: build_outline_tree keys nodes by `position`, so when two live
        # items collide on the same position (a data bug we also guard against
        # elsewhere) one overwrites the other in the map and disappears from
        # the tree. A tree-based cascade would then miss the shadowed sibling
        # and leave it orphaned after its parent is deleted. parent_bid gives a
        # deterministic closure that is immune to position collisions.
        existing_items = __get_existing_outline_items(unit_to_delete.shifu_bid)
        children_by_parent: dict[str, list[str]] = {}
        for item in existing_items:
            children_by_parent.setdefault(item.parent_bid, []).append(
                item.outline_item_bid
            )

        ids_to_delete = []
        seen = set()
        stack = [unit_id]
        while stack:
            current = stack.pop()
            if current in seen:
                # Defensive: a corrupted parent_bid cycle must not loop forever.
                continue
            seen.add(current)
            ids_to_delete.append(current)
            stack.extend(children_by_parent.get(current, []))

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
        for item_id in ids_to_delete:
            cleanup_outline_history_versions(app, unit_to_delete.shifu_bid, item_id)
        delete_outline_history(app, user_id, unit_to_delete.shifu_bid, unit_id)
        db.session.commit()
        return True
