"""Offline repair helpers for broken draft outline structures."""

from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass, field

from flask import Flask

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.util.datetime import now_utc

from .models import DraftOutlineItem, DraftShifu
from .shifu_history_manager import save_outline_tree_history
from .shifu_outline_funcs import (
    __lock_shifu_for_outline_write,
    build_outline_history_tree_from_outlines,
)


@dataclass
class OutlineStructureChange:
    outline_item_bid: str
    old_parent_bid: str
    new_parent_bid: str
    old_position: str
    new_position: str

    def to_payload(self) -> dict:
        return {
            "outline_item_bid": self.outline_item_bid,
            "old_parent_bid": self.old_parent_bid,
            "new_parent_bid": self.new_parent_bid,
            "old_position": self.old_position,
            "new_position": self.new_position,
        }


@dataclass
class OutlineStructureRepairRecord:
    shifu_bid: str
    shifu_title: str
    issue_types: list[str]
    changed_outlines: list[OutlineStructureChange] = field(default_factory=list)
    retired_outline_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "shifu_bid": self.shifu_bid,
            "shifu_title": self.shifu_title,
            "issue_types": self.issue_types,
            "changed_outline_count": len(self.changed_outlines),
            "changed_outlines": [item.to_payload() for item in self.changed_outlines],
            "retired_outline_count": len(self.retired_outline_bids),
            "retired_outline_bids": self.retired_outline_bids,
        }


@dataclass
class OutlineStructureSkippedRecord:
    shifu_bid: str
    reason: str

    def to_payload(self) -> dict:
        return {
            "shifu_bid": self.shifu_bid,
            "reason": self.reason,
        }


@dataclass
class OutlineStructureRepairResult:
    status: str
    dry_run: bool
    scanned_shifu_count: int
    repaired_shifu_count: int
    changed_outline_count: int
    retired_outline_count: int
    rebuilt_struct_count: int
    repaired_records: list[OutlineStructureRepairRecord] = field(default_factory=list)
    skipped_records: list[OutlineStructureSkippedRecord] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "scanned_shifu_count": self.scanned_shifu_count,
            "repaired_shifu_count": self.repaired_shifu_count,
            "changed_outline_count": self.changed_outline_count,
            "retired_outline_count": self.retired_outline_count,
            "rebuilt_struct_count": self.rebuilt_struct_count,
            "repaired_records": [item.to_payload() for item in self.repaired_records],
            "skipped_records": [item.to_payload() for item in self.skipped_records],
        }


def _apply_shifu_scope(query, shifu_bids: list[str] | str | None):
    if shifu_bids is None:
        return query
    if isinstance(shifu_bids, str):
        return query.filter(DraftOutlineItem.shifu_bid == shifu_bids)
    return query.filter(DraftOutlineItem.shifu_bid.in_(shifu_bids))


def _load_latest_active_outline_items(
    shifu_bids: list[str] | str | None = None,
) -> list[DraftOutlineItem]:
    if shifu_bids is not None and not shifu_bids:
        return []

    latest_ids_query = db.session.query(db.func.max(DraftOutlineItem.id).label("id"))
    latest_ids_query = _apply_shifu_scope(latest_ids_query, shifu_bids)
    latest_ids = latest_ids_query.group_by(
        DraftOutlineItem.shifu_bid,
        DraftOutlineItem.outline_item_bid,
    ).subquery()
    query = DraftOutlineItem.query.filter(
        DraftOutlineItem.id.in_(db.session.query(latest_ids.c.id)),
        DraftOutlineItem.deleted == 0,
    )
    query = _apply_shifu_scope(query, shifu_bids)
    return query.order_by(
        DraftOutlineItem.shifu_bid.asc(),
        DraftOutlineItem.position.asc(),
        DraftOutlineItem.id.asc(),
    ).all()


def _detect_issue_types(items: list[DraftOutlineItem]) -> list[str]:
    positions: dict[str, int] = defaultdict(int)
    current_bids = {item.outline_item_bid for item in items}
    positions_by_bid = {item.outline_item_bid: item.position or "" for item in items}
    issue_types: set[str] = set()
    for item in items:
        positions[item.position] += 1
        position_len = len(item.position or "")
        if position_len == 0 or position_len % 2 != 0:
            issue_types.add("invalid_position_format")
        if len(item.position or "") > 2 and not (
            item.parent_bid and item.parent_bid in current_bids
        ):
            issue_types.add("parent_mismatch")
        if (
            position_len > 2
            and item.parent_bid
            and item.parent_bid in current_bids
            and positions_by_bid.get(item.parent_bid, "") != (item.position or "")[:-2]
        ):
            issue_types.add("parent_position_mismatch")
        if len(item.position or "") == 2 and item.parent_bid:
            issue_types.add("root_parent_mismatch")
    if any(count > 1 for count in positions.values()):
        issue_types.add("position_collision")
    return sorted(issue_types)


def _plan_outline_structure_repair(
    items: list[DraftOutlineItem],
) -> tuple[list[OutlineStructureChange], str | None]:
    if not items:
        return [], None

    by_bid = {item.outline_item_bid: item for item in items}
    position_to_items: dict[str, list[DraftOutlineItem]] = defaultdict(list)
    for item in items:
        position_to_items[item.position].append(item)

    resolved_parent_by_bid: dict[str, str] = {}
    children_by_parent: dict[str, list[DraftOutlineItem]] = defaultdict(list)

    for item in items:
        position = item.position or ""
        if not position or len(position) % 2 != 0:
            return (
                [],
                f"Unsupported position format for outline {item.outline_item_bid}: {position!r}",
            )

        if len(position) == 2:
            parent_bid = ""
        elif (
            item.parent_bid
            and item.parent_bid in by_bid
            and item.parent_bid != item.outline_item_bid
        ):
            parent_bid = item.parent_bid
        else:
            parent_position = position[:-2]
            parent_candidates = position_to_items.get(parent_position, [])
            if len(parent_candidates) != 1:
                return [], (
                    "Cannot infer unique parent for outline "
                    f"{item.outline_item_bid} from parent position {parent_position!r}"
                )
            parent_bid = parent_candidates[0].outline_item_bid
            if parent_bid == item.outline_item_bid:
                return [], f"Outline {item.outline_item_bid} would parent itself"

        resolved_parent_by_bid[item.outline_item_bid] = parent_bid
        children_by_parent[parent_bid].append(item)

    for siblings in children_by_parent.values():
        siblings.sort(key=lambda item: (item.position or "", item.id))

    assigned_positions: dict[str, str] = {}
    visited: set[str] = set()

    def _preferred_suffix(item: DraftOutlineItem, prefix: str | None) -> int:
        position = item.position or ""
        if prefix and position.startswith(prefix) and len(position) == len(prefix) + 2:
            suffix_part = position[-2:]
            if suffix_part.isdigit():
                return max(int(suffix_part), 1)
        if not prefix and len(position) == 2 and position.isdigit():
            return max(int(position), 1)
        if len(position) >= 2 and position[-2:].isdigit():
            return max(int(position[-2:]), 1)
        return 1

    def _next_available_suffix(used_suffixes: set[int], desired_suffix: int) -> int:
        suffix = max(desired_suffix, 1)
        while suffix in used_suffixes:
            suffix += 1
        return suffix

    def _walk(parent_bid: str, prefix: str) -> None:
        used_suffixes: set[int] = set()
        siblings = children_by_parent.get(parent_bid, [])
        for item in siblings:
            bid = item.outline_item_bid
            if bid in visited:
                raise RuntimeError(f"Cycle detected around outline {bid}")
            visited.add(bid)
            next_suffix = _next_available_suffix(
                used_suffixes,
                _preferred_suffix(item, prefix),
            )
            used_suffixes.add(next_suffix)
            next_position = (
                f"{prefix}{next_suffix:02d}" if prefix else f"{next_suffix:02d}"
            )
            assigned_positions[bid] = next_position
            _walk(bid, next_position)

    try:
        _walk("", "")
    except RuntimeError as exc:
        return [], str(exc)

    if len(visited) != len(items):
        unresolved = sorted(set(by_bid) - visited)
        return (
            [],
            f"Unreachable outlines after repair planning: {', '.join(unresolved)}",
        )

    changes: list[OutlineStructureChange] = []
    for item in items:
        new_parent_bid = resolved_parent_by_bid[item.outline_item_bid]
        new_position = assigned_positions[item.outline_item_bid]
        old_parent_bid = item.parent_bid or ""
        old_position = item.position or ""
        if old_parent_bid == new_parent_bid and old_position == new_position:
            continue
        changes.append(
            OutlineStructureChange(
                outline_item_bid=item.outline_item_bid,
                old_parent_bid=old_parent_bid,
                new_parent_bid=new_parent_bid,
                old_position=old_position,
                new_position=new_position,
            )
        )
    return changes, None


def _normalize_bid_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        bid = str(value or "").strip()
        if bid and bid not in seen:
            normalized.append(bid)
            seen.add(bid)
    return normalized


def _collect_retired_duplicate_root_bids(
    items: list[DraftOutlineItem],
    keep_root_bids: list[str],
) -> tuple[list[str], str | None]:
    if not keep_root_bids:
        return [], None

    by_bid = {str(item.outline_item_bid or "").strip(): item for item in items}
    missing_keep_bids = [bid for bid in keep_root_bids if bid not in by_bid]
    if missing_keep_bids:
        return [], f"Keep root outline not found: {', '.join(missing_keep_bids)}"

    keep_roots = [by_bid[bid] for bid in keep_root_bids]
    non_root_keep_bids = [
        bid
        for bid, item in zip(keep_root_bids, keep_roots)
        if str(item.parent_bid or "").strip()
    ]
    if non_root_keep_bids:
        return [], f"Keep outline is not a root: {', '.join(non_root_keep_bids)}"

    keep_positions_by_bid = {
        bid: str(item.position or "").strip()
        for bid, item in zip(keep_root_bids, keep_roots)
    }
    keep_bids_by_position: dict[str, list[str]] = defaultdict(list)
    for bid, position in keep_positions_by_bid.items():
        keep_bids_by_position[position].append(bid)
    duplicated_keep_positions = {
        position: bids
        for position, bids in keep_bids_by_position.items()
        if len(bids) > 1
    }
    if duplicated_keep_positions:
        details = ", ".join(
            f"{position}: {', '.join(bids)}"
            for position, bids in sorted(duplicated_keep_positions.items())
        )
        return [], f"Keep root outlines must have unique positions: {details}"

    children_by_parent: dict[str, list[DraftOutlineItem]] = defaultdict(list)
    for item in items:
        children_by_parent[str(item.parent_bid or "").strip()].append(item)

    keep_positions = set(keep_positions_by_bid.values())
    keep_bid_set = set(keep_root_bids)
    duplicate_root_bids = [
        str(item.outline_item_bid or "").strip()
        for item in children_by_parent.get("", [])
        if str(item.outline_item_bid or "").strip()
        and str(item.position or "").strip() in keep_positions
        and str(item.outline_item_bid or "").strip() not in keep_bid_set
    ]

    retired: list[str] = []
    seen: set[str] = set()

    def _walk_retired_subtree(outline_bid: str) -> None:
        if not outline_bid:
            return
        if outline_bid in seen:
            return
        seen.add(outline_bid)
        retired.append(outline_bid)
        for child in children_by_parent.get(outline_bid, []):
            child_bid = str(child.outline_item_bid or "").strip()
            if child_bid:
                _walk_retired_subtree(child_bid)

    for outline_bid in duplicate_root_bids:
        _walk_retired_subtree(outline_bid)

    return retired, None


def repair_shifu_outline_structure(
    app: Flask,
    *,
    user_bid: str | None,
    shifu_bids: list[str] | None = None,
    keep_root_bids: list[str] | None = None,
    dry_run: bool = False,
) -> OutlineStructureRepairResult:
    if not dry_run and not user_bid:
        raise ValueError("user_bid is required when dry_run is False")

    normalized_keep_root_bids = _normalize_bid_list(keep_root_bids)
    if normalized_keep_root_bids and (not shifu_bids or len(shifu_bids) != 1):
        raise ValueError("keep_root_bids requires exactly one shifu_bid")

    with app.app_context():
        items = _load_latest_active_outline_items(shifu_bids)
        items_by_shifu: dict[str, list[DraftOutlineItem]] = defaultdict(list)
        for item in items:
            items_by_shifu[item.shifu_bid].append(item)

        target_shifu_bids = (
            sorted(items_by_shifu.keys()) if shifu_bids is None else list(shifu_bids)
        )
        shifu_titles = {
            row.shifu_bid: row.title
            for row in DraftShifu.query.filter(
                DraftShifu.shifu_bid.in_(target_shifu_bids),
                DraftShifu.deleted == 0,
            ).all()
        }

        repaired_records: list[OutlineStructureRepairRecord] = []
        skipped_records: list[OutlineStructureSkippedRecord] = []
        rebuilt_struct_count = 0
        changed_outline_count = 0
        retired_outline_count = 0

        transaction_scope = nullcontext() if dry_run else unit_of_work()
        with transaction_scope:
            for shifu_bid in target_shifu_bids:
                shifu_items = items_by_shifu.get(shifu_bid, [])
                if not shifu_items:
                    continue

                issue_types = _detect_issue_types(shifu_items)
                retired_outline_bids: list[str] = []
                if normalized_keep_root_bids:
                    retired_outline_bids, skip_reason = (
                        _collect_retired_duplicate_root_bids(
                            shifu_items,
                            normalized_keep_root_bids,
                        )
                    )
                    if skip_reason:
                        skipped_records.append(
                            OutlineStructureSkippedRecord(
                                shifu_bid=shifu_bid,
                                reason=skip_reason,
                            )
                        )
                        continue
                    if retired_outline_bids:
                        issue_types = sorted(
                            set(issue_types) | {"root_generation_collision"}
                        )
                        retired_bid_set = set(retired_outline_bids)
                        shifu_items = [
                            item
                            for item in shifu_items
                            if str(item.outline_item_bid or "").strip()
                            not in retired_bid_set
                        ]
                if not issue_types:
                    continue

                changes, skip_reason = _plan_outline_structure_repair(shifu_items)
                if skip_reason:
                    skipped_records.append(
                        OutlineStructureSkippedRecord(
                            shifu_bid=shifu_bid,
                            reason=skip_reason,
                        )
                    )
                    continue

                if not changes:
                    if not retired_outline_bids:
                        continue

                record = OutlineStructureRepairRecord(
                    shifu_bid=shifu_bid,
                    shifu_title=shifu_titles.get(shifu_bid, ""),
                    issue_types=issue_types,
                    changed_outlines=changes,
                    retired_outline_bids=retired_outline_bids,
                )
                repaired_records.append(record)
                changed_outline_count += len(changes)
                retired_outline_count += len(retired_outline_bids)

                if dry_run:
                    continue

                __lock_shifu_for_outline_write(shifu_bid)
                locked_items = _load_latest_active_outline_items(shifu_bid)
                locked_issue_types = _detect_issue_types(locked_items)
                locked_retired_outline_bids: list[str] = []
                skip_reason = None
                if normalized_keep_root_bids:
                    locked_retired_outline_bids, skip_reason = (
                        _collect_retired_duplicate_root_bids(
                            locked_items,
                            normalized_keep_root_bids,
                        )
                    )
                    if skip_reason is None:
                        locked_retired_bid_set = set(locked_retired_outline_bids)
                        locked_items = [
                            item
                            for item in locked_items
                            if str(item.outline_item_bid or "").strip()
                            not in locked_retired_bid_set
                        ]
                    if locked_retired_outline_bids:
                        locked_issue_types = sorted(
                            set(locked_issue_types) | {"root_generation_collision"}
                        )
                if skip_reason is None:
                    changes, skip_reason = _plan_outline_structure_repair(locked_items)
                if skip_reason:
                    repaired_records.pop()
                    changed_outline_count -= len(record.changed_outlines)
                    retired_outline_count -= len(record.retired_outline_bids)
                    skipped_records.append(
                        OutlineStructureSkippedRecord(
                            shifu_bid=shifu_bid,
                            reason=skip_reason,
                        )
                    )
                    continue
                if not changes and not locked_retired_outline_bids:
                    repaired_records.pop()
                    changed_outline_count -= len(record.changed_outlines)
                    retired_outline_count -= len(record.retired_outline_bids)
                    continue
                changed_outline_count += len(changes) - len(record.changed_outlines)
                retired_outline_count += len(locked_retired_outline_bids) - len(
                    record.retired_outline_bids
                )
                record.changed_outlines = changes
                record.retired_outline_bids = locked_retired_outline_bids
                record.issue_types = locked_issue_types

                current_time = now_utc()
                change_by_bid = {
                    str(item.outline_item_bid or "").strip(): item for item in changes
                }
                retired_bid_set = set(locked_retired_outline_bids)
                for item in _load_latest_active_outline_items(shifu_bid):
                    outline_bid = str(item.outline_item_bid or "").strip()
                    change = change_by_bid.get(outline_bid)
                    if not change and outline_bid not in retired_bid_set:
                        continue
                    new_item = item.clone()
                    if change:
                        new_item.parent_bid = change.new_parent_bid
                        new_item.position = change.new_position
                    if outline_bid in retired_bid_set:
                        new_item.deleted = 1
                    new_item.updated_user_bid = user_bid
                    new_item.updated_at = current_time
                    db.session.add(new_item)

                db.session.flush()

                latest_items = _load_latest_active_outline_items(shifu_bid)
                history_tree = build_outline_history_tree_from_outlines(latest_items)
                shifu_db_row = (
                    DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0)
                    .order_by(DraftShifu.id.desc())
                    .first()
                )
                save_outline_tree_history(
                    app=app,
                    user_id=user_bid,
                    shifu_bid=shifu_bid,
                    outline_tree=history_tree,
                    shifu_id=shifu_db_row.id if shifu_db_row else None,
                )
                rebuilt_struct_count += 1

        status = "noop"
        if repaired_records:
            status = "dry_run" if dry_run else "repaired"
        elif skipped_records:
            status = "skipped"

        return OutlineStructureRepairResult(
            status=status,
            dry_run=dry_run,
            scanned_shifu_count=len(target_shifu_bids),
            repaired_shifu_count=len(repaired_records),
            changed_outline_count=changed_outline_count,
            retired_outline_count=retired_outline_count,
            rebuilt_struct_count=rebuilt_struct_count,
            repaired_records=repaired_records,
            skipped_records=skipped_records,
        )
