"""Freeze authorized published course rows without starting or mutating the app."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from collections import defaultdict
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .state import ArenaError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask
    from sqlalchemy.orm import Session


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


@contextmanager
def _read_session(app: Flask) -> Iterator[Session]:
    """Use an independent consistent read, with no ORM autoflush or commit."""
    from flaskr.dao import db
    from sqlalchemy.orm import Session

    with app.app_context():
        engine = db.engine
        isolation = (
            "REPEATABLE READ"
            if engine.dialect.name in {"mysql", "postgresql"}
            else "SERIALIZABLE"
        )
        with (
            engine.connect().execution_options(isolation_level=isolation) as connection,
            Session(
                bind=connection, autoflush=False, expire_on_commit=False
            ) as session,
        ):
            yield session


def _viewable_course_ids(session: Session, owner_user_bid: str) -> set[str]:
    """Mirror authoring VIEW semantics, deliberately excluding publish-only grants."""
    from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedShifu
    from flaskr.service.shifu.permissions import (
        _auth_types_to_permissions,
        _normalize_auth_types,
    )
    from flaskr.service.user.models import UserInfo
    from sqlalchemy import select

    if (
        session.scalar(
            select(UserInfo.id)
            .where(UserInfo.user_bid == owner_user_bid, UserInfo.deleted == 0)
            .limit(1)
        )
        is None
    ):
        return set()
    candidates = set()
    for model in (DraftShifu, PublishedShifu):
        candidates.update(
            session.scalars(
                select(model.shifu_bid).where(
                    model.created_user_bid == owner_user_bid, model.deleted == 0
                )
            )
        )
    owned = set()
    for shifu_bid in candidates:
        for model in (DraftShifu, PublishedShifu):
            creator = session.scalar(
                select(model.created_user_bid)
                .where(model.shifu_bid == shifu_bid, model.deleted == 0)
                .order_by(model.id.desc())
                .limit(1)
            )
            if creator:
                if creator == owner_user_bid:
                    owned.add(shifu_bid)
                break
    grants = session.scalars(
        select(AiCourseAuth)
        .where(AiCourseAuth.user_id == owner_user_bid, AiCourseAuth.status == 1)
        .order_by(AiCourseAuth.id.asc())
    )
    seen_grants = set()
    for grant in grants:
        if grant.course_id in seen_grants:
            continue
        seen_grants.add(grant.course_id)
        if "view" in _auth_types_to_permissions(_normalize_auth_types(grant.auth_type)):
            owned.add(grant.course_id)
    return owned


def _outline_paths(structure: dict) -> list[tuple[dict, list[int]]]:
    """Validate the published tree and retain parent row IDs in nearest-first order."""
    result = []
    seen = set()

    def visit(node: dict, parents: list[int]) -> None:
        if not isinstance(node, dict) or node.get("type") not in {"shifu", "outline"}:
            message = "Invalid published structure node"
            raise ArenaError(message)
        row_id = node.get("id")
        if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id <= 0:
            message = "Published structure has an invalid row ID"
            raise ArenaError(message)
        identity = (node["type"], row_id)
        if identity in seen:
            message = "Published structure contains duplicate rows"
            raise ArenaError(message)
        seen.add(identity)
        if node["type"] == "outline":
            result.append((node, parents))
            parents = [row_id, *parents]
        for child in node.get("children") or []:
            visit(child, parents)

    visit(structure, [])
    return result


def _load_published_lessons(session: Session, shifu_bid: str) -> list[dict]:
    from flaskr.service.shifu.models import (
        LogPublishedStruct,
        PublishedOutlineItem,
        PublishedShifu,
    )
    from flaskr.util.datetime import to_utc_iso
    from sqlalchemy import select

    record = session.scalar(
        select(LogPublishedStruct)
        .where(
            LogPublishedStruct.shifu_bid == shifu_bid, LogPublishedStruct.deleted == 0
        )
        .order_by(LogPublishedStruct.id.desc())
        .limit(1)
    )
    if record is None:
        return []
    structure = json.loads(record.struct)
    if (
        not isinstance(structure, dict)
        or structure.get("type") != "shifu"
        or structure.get("bid") != shifu_bid
    ):
        message = "Published structure has an invalid course root"
        raise ArenaError(message)
    paths = _outline_paths(structure)
    course = session.get(PublishedShifu, structure["id"])
    if course is None or course.deleted or course.shifu_bid != shifu_bid:
        message = "Published course row is unavailable"
        raise ArenaError(message)
    row_ids = [node["id"] for node, _ in paths]
    outlines = {
        row.id: row
        for row in session.scalars(
            select(PublishedOutlineItem).where(PublishedOutlineItem.id.in_(row_ids))
        )
    }
    result = []
    for node, parents in paths:
        row = outlines.get(node["id"])
        if (
            row is None
            or row.deleted
            or row.shifu_bid != shifu_bid
            or row.outline_item_bid != node.get("bid")
        ):
            message = (
                "Published outline row is unavailable or belongs to another course"
            )
            raise ArenaError(message)
        prompt_chain = [row, *(outlines[parent] for parent in parents), course]
        document_prompt = next(
            (
                str(item.llm_system_prompt).strip()
                for item in prompt_chain
                if str(item.llm_system_prompt or "").strip()
            ),
            "",
        )
        source = {
            "shifu_bid": shifu_bid,
            "outline_bid": row.outline_item_bid,
            "published_struct_id": record.id,
            "published_struct_bid": record.struct_bid,
            "published_shifu_id": course.id,
            "published_outline_id": row.id,
            "published_at": to_utc_iso(record.created_at),
            "course_title": course.title,
            "outline_title": row.title,
        }
        lesson = {
            "source": source,
            "document": row.content or "",
            "document_prompt": document_prompt,
            "prompt_chain": [
                {
                    "kind": kind,
                    "row_id": item.id,
                    "prompt": item.llm_system_prompt or "",
                }
                for kind, item in [
                    ("course", course),
                    *(("parent", outlines[parent]) for parent in reversed(parents)),
                    ("lesson", row),
                ]
            ],
            "use_learner_language": bool(course.use_learner_language),
        }
        source["content_hash"] = _digest(lesson)
        result.append(lesson)
    return result


def resolve_owner_user_bid(app: Flask, owner_phone: str) -> str:
    """Resolve precisely the single account selected by normal phone sign-in."""
    from flaskr.service.common.phone_numbers import normalize_phone_identifier
    from flaskr.service.user.models import AuthCredential, UserInfo
    from sqlalchemy import select

    identifier = normalize_phone_identifier(owner_phone.strip())
    if not identifier:
        message = "An owner phone identifier is required"
        raise ArenaError(message)
    # PhoneAuthProvider.verify and verify_phone_code normalize before calling
    # repository.load_user_aggregate_by_identifier. That lookup chooses the
    # oldest active canonical entity first, then the oldest phone credential.
    # Mirror that read-only ordering instead of combining legacy same-phone
    # accounts or expanding phone spellings beyond the login contract.
    with _read_session(app) as session:
        owner_user_bid = session.scalar(
            select(UserInfo.user_bid)
            .where(UserInfo.user_identify == identifier, UserInfo.deleted == 0)
            .order_by(UserInfo.id.asc())
            .limit(1)
        )
        if owner_user_bid is None:
            credential_user_bid = session.scalar(
                select(AuthCredential.user_bid)
                .where(
                    AuthCredential.provider_name == "phone",
                    AuthCredential.identifier == identifier,
                    AuthCredential.deleted == 0,
                )
                .order_by(AuthCredential.id.asc())
                .limit(1)
            )
            # Do not skip an orphaned/deleted first credential to reach a later
            # same-phone account: normal login does not make that fallback.
            owner_user_bid = session.scalar(
                select(UserInfo.user_bid)
                .where(
                    UserInfo.user_bid == credential_user_bid,
                    UserInfo.deleted == 0,
                )
                .limit(1)
            )
    if not owner_user_bid:
        message = (
            "Owner phone does not resolve to an active account through phone login"
        )
        raise ArenaError(message)
    return owner_user_bid


def snapshot_courses(app: Flask, owner_phone: str) -> dict:
    """Export only courses whose published prompts the resolved owner can view."""
    owner_user_bid = resolve_owner_user_bid(app, owner_phone)
    courses, skipped = [], []
    with _read_session(app) as session:
        for shifu_bid in sorted(_viewable_course_ids(session, owner_user_bid)):
            try:
                lessons = _load_published_lessons(session, shifu_bid)
            except (ArenaError, ValueError, KeyError, TypeError):
                skipped.append(
                    {"shifu_bid": shifu_bid, "reason": "invalid_published_structure"}
                )
                continue
            if not lessons:
                skipped.append({"shifu_bid": shifu_bid, "reason": "not_published"})
            courses.extend(lessons)
    return {
        "owner_user_bid": owner_user_bid,
        "owner_resolution_method": "phone_login_canonical",
        "courses": courses,
        "skipped": skipped,
    }


def revalidate_sources(app: Flask, owner_user_bid: str, cases: list[dict]) -> set[str]:
    """Recheck current VIEW permission and the exact published snapshot before export."""
    valid = set()
    by_course = defaultdict(list)
    for case in cases:
        by_course[case["source"]["shifu_bid"]].append(case)
    with _read_session(app) as session:
        allowed = _viewable_course_ids(session, owner_user_bid)
        for shifu_bid, course_cases in by_course.items():
            if shifu_bid not in allowed:
                continue
            try:
                current = {
                    lesson["source"]["published_outline_id"]: lesson
                    for lesson in _load_published_lessons(session, shifu_bid)
                }
            except (ArenaError, ValueError, KeyError, TypeError):
                continue
            for case in course_cases:
                lesson = current.get(case["source"]["published_outline_id"])
                if lesson and lesson["source"] == case["source"]:
                    valid.add(case["case_id"])
    return valid


def case_input_hash(case: dict) -> str:
    """Hash only the frozen model input, independently of model and output identity."""
    fields = (
        "document",
        "document_prompt",
        "block_index",
        "variables",
        "context",
        "user_input",
        "output_language",
        "use_learner_language",
        "interaction_prompt",
        "interaction_error_prompt",
        "temperature",
    )
    return _digest({key: case.get(key) for key in fields})


def requests_slides(content: str, inherited_prompt: str = "") -> bool:
    """Require slide-generation intent, rather than generic HTML or visual content."""
    verbs = r"(?:生成|制作|创建|输出|设计|呈现|展示|绘制|使用|用|做|create|generate|make|render|present|use)"
    slides = r"(?:幻灯片|PPT|slides?\b)"
    numbered = r"(?:画面|幻灯片|slide)\s*\d+\s*[:\uFF1A]"
    conditional = (
        r"(?:只有|仅当|仅在|只在|如果|当要求|\bonly\s+(?:on|upon)\b|\bwhen\b|\bif\b)"
    )
    negated = r"(?:不要|不生成|不创建|禁止|\bnot\b|\bnever\b)"
    for text in (content, inherited_prompt):
        for sentence in re.split(r"[\n。.!?;\uFF1B]", text):
            clauses = re.split(r"[,\uFF0C]", sentence)
            conditional_prefix = False
            for index, clause in enumerate(clauses):
                conditional_prefix |= bool(
                    re.search(conditional, clause, re.IGNORECASE)
                )
                match = re.search(
                    verbs + r"[^\n。.!?]{0,60}" + slides,
                    clause,
                    re.IGNORECASE,
                ) or re.search(numbered, clause, re.IGNORECASE)
                if not match or conditional_prefix:
                    continue
                # A condition after a comma still qualifies the slide command.
                if index + 1 < len(clauses) and re.match(
                    r"\s*(?:" + conditional + r")", clauses[index + 1], re.IGNORECASE
                ):
                    continue
                # Negative layout constraints after an affirmative command do
                # not negate slide generation. Check only its command prefix.
                if re.search(negated, clause[: match.end()], re.IGNORECASE):
                    continue
                return True
    return False


def prepare_cases(snapshot: dict, count: int, seed: int, variables: dict) -> list[dict]:
    """Deterministically sample independent content blocks with complete fixed variables."""
    from markdown_flow import (
        BlockType,
        InteractionParser,
        MarkdownFlow,
        extract_variables_from_text,
    )

    if count <= 0:
        message = "Case count must be positive"
        raise ArenaError(message)
    fixed_variables = copy.deepcopy(variables)
    language = str(
        fixed_variables.get("language")
        or fixed_variables.get("sys_user_language")
        or "zh-CN"
    )
    fixed_variables.update({"language": language, "sys_user_language": language})
    buckets = defaultdict(lambda: defaultdict(list))
    skipped = snapshot.setdefault("skipped", [])

    def skip(
        lesson: dict, block_index: int, reason: str, missing: list[str] | None = None
    ) -> None:
        entry = {
            "shifu_bid": lesson["source"].get("shifu_bid", ""),
            "outline_bid": lesson["source"].get("outline_bid", ""),
            "block_index": block_index,
            "reason": reason,
        }
        if missing:
            entry["missing_variables"] = missing
        if entry not in skipped:
            skipped.append(entry)

    for lesson in snapshot["courses"]:
        flow = MarkdownFlow(document=lesson["document"])
        blocks = flow.get_all_blocks()
        requires_prior_context = False
        for block in blocks:
            if not block.content.strip():
                continue
            if block.block_type == BlockType.PRESERVED_CONTENT:
                skip(lesson, block.index, "preserved_content")
                # Normal preview/learning history includes this static output.
                # Its successor cannot be evaluated with an empty conversation.
                requires_prior_context = True
                continue
            if requires_prior_context:
                skip(lesson, block.index, "prior_context_required")
                continue
            requires_prior_context = True
            if block.block_type != BlockType.CONTENT:
                skip(lesson, block.index, "prior_context_required")
                continue
            required = set(extract_variables_from_text(block.content)) | set(
                extract_variables_from_text(lesson["document_prompt"])
            )
            next_index = block.index + 1
            if (
                next_index < len(blocks)
                and blocks[next_index].block_type == BlockType.INTERACTION
            ):
                # markdown-flow adds the next question/options to this content
                # request. Only their displayed text is input; the interaction
                # assignment target does not yet need a learner answer.
                interaction = InteractionParser().parse(blocks[next_index].content)
                displays = [
                    interaction.get("question", ""),
                    *(
                        button.get("display", "")
                        for button in interaction.get("buttons", [])
                    ),
                ]
                for display in displays:
                    required.update(extract_variables_from_text(display))
            missing = sorted(required.difference(fixed_variables))
            if missing:
                skip(lesson, block.index, "missing_variables", missing)
                continue
            if not requests_slides(block.content, lesson["document_prompt"]):
                skip(lesson, block.index, "not_slide_generation")
                continue
            category = "slides"
            case = {
                **copy.deepcopy(lesson),
                "owner_user_bid": snapshot["owner_user_bid"],
                "block_index": block.index,
                "variables": copy.deepcopy(fixed_variables),
                "context": [],
                "user_input": None,
                "output_language": language,
                "temperature": 0.3,
                "category": category,
                "task_description": "Render the frozen published slide generation.",
            }
            case["input_hash"] = case_input_hash(case)
            case["case_id"] = _digest(
                {"source": case["source"], "input_hash": case["input_hash"]}
            )[:24]
            buckets[lesson["source"].get("shifu_bid", "")][category].append(case)
    rng = random.Random(seed)  # noqa: S311 - seeded sampling is reproducibility, not security.
    course_order = sorted(buckets)
    rng.shuffle(course_order)
    for course_buckets in buckets.values():
        for category in sorted(course_buckets):
            candidates = course_buckets[category]
            candidates.sort(key=lambda item: item["case_id"])
            rng.shuffle(candidates)
    result = []
    category_counts = defaultdict(int)
    while len(result) < count:
        made_progress = False
        for shifu_bid in course_order:
            available = [
                category for category, values in buckets[shifu_bid].items() if values
            ]
            if not available:
                continue
            category = min(available, key=lambda item: (category_counts[item], item))
            result.append(buckets[shifu_bid][category].pop())
            category_counts[category] += 1
            made_progress = True
            if len(result) == count:
                break
        if not made_progress:
            break
    if len(result) < count:
        message = f"Only {len(result)} eligible published content blocks are available; requested {count}"
        raise ArenaError(message)
    return result
