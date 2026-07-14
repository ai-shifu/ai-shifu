"""Offline repair helpers for broken draft outline structures."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from flask import Flask

from flaskr.dao import db
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

    def to_payload(self) -> dict:
        return {
            "shifu_bid": self.shifu_bid,
            "shifu_title": self.shifu_title,
            "issue_types": self.issue_types,
            "changed_outline_count": len(self.changed_outlines),
            "changed_outlines": [item.to_payload() for item in self.changed_outlines],
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


def repair_shifu_outline_structure(
    app: Flask,
    *,
    user_bid: str | None,
    shifu_bids: list[str] | None = None,
    dry_run: bool = False,
) -> OutlineStructureRepairResult:
    if not dry_run and not user_bid:
        raise ValueError("user_bid is required when dry_run is False")

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

        for shifu_bid in target_shifu_bids:
            shifu_items = items_by_shifu.get(shifu_bid, [])
            if not shifu_items:
                continue

            issue_types = _detect_issue_types(shifu_items)
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
                continue

            record = OutlineStructureRepairRecord(
                shifu_bid=shifu_bid,
                shifu_title=shifu_titles.get(shifu_bid, ""),
                issue_types=issue_types,
                changed_outlines=changes,
            )
            repaired_records.append(record)
            changed_outline_count += len(changes)

            if dry_run:
                continue

            __lock_shifu_for_outline_write(shifu_bid)
            locked_items = _load_latest_active_outline_items(shifu_bid)
            changes, skip_reason = _plan_outline_structure_repair(locked_items)
            if skip_reason:
                repaired_records.pop()
                changed_outline_count -= len(record.changed_outlines)
                skipped_records.append(
                    OutlineStructureSkippedRecord(
                        shifu_bid=shifu_bid,
                        reason=skip_reason,
                    )
                )
                continue
            if not changes:
                repaired_records.pop()
                changed_outline_count -= len(record.changed_outlines)
                continue
            changed_outline_count += len(changes) - len(record.changed_outlines)
            record.changed_outlines = changes

            current_time = now_utc()
            change_by_bid = {item.outline_item_bid: item for item in changes}
            for item in locked_items:
                change = change_by_bid.get(item.outline_item_bid)
                if not change:
                    continue
                new_item = item.clone()
                new_item.parent_bid = change.new_parent_bid
                new_item.position = change.new_position
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

        if not dry_run and (repaired_records or skipped_records):
            db.session.commit()

        if not dry_run and not repaired_records and not skipped_records:
            db.session.rollback()

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
            rebuilt_struct_count=rebuilt_struct_count,
            repaired_records=repaired_records,
            skipped_records=skipped_records,
        )
