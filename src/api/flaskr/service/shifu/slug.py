"""Versioned public slug generation and resolution for shifus."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Iterable

from flask import Flask, current_app, has_app_context
from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError, OperationalError

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.dao import db
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.util.prompt_loader import load_prompt_template

from .models import (
    DraftShifu,
    PublishedShifu,
    ShifuCourseSlug,
    ShifuPublicIdentifier,
)


SLUG_MIN_LENGTH = 18
SLUG_MAX_LENGTH = 48
SLUG_MIN_WORDS = 3
SLUG_MAX_WORDS = 6
SLUG_GENERATION_ATTEMPTS = 2
SLUG_ALLOCATION_TRANSACTION_ATTEMPTS = 3

_MYSQL_RETRYABLE_TRANSACTION_ERRORS = {1205, 1213}
_MYSQL_MISSING_SAVEPOINT_ERROR = 1305

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_RESERVED_SLUGS = {
    "admin",
    "api",
    "c",
    "course",
    "courses",
    "learn",
    "login",
    "logout",
    "new",
    "preview",
    "shifu",
}


class InvalidCourseSlug(ValueError):
    """Raised when a model candidate does not satisfy the public contract."""


class ShifuIdentifierConflict(ValueError):
    """Raised when a new BID collides with an existing public slug."""


@dataclass(frozen=True)
class PreparedCourseSlug:
    base_slug: str
    generation_source: str


@dataclass(frozen=True)
class SlugAllocation:
    binding: ShifuCourseSlug
    created: bool
    collided: bool


def _app_context_if_needed(app: Flask):
    if has_app_context() and current_app._get_current_object() is app:
        return nullcontext()
    return app.app_context()


def validate_course_slug(slug: str) -> str:
    """Validate and return one normal model-generated slug."""

    normalized = str(slug or "")
    if normalized != normalized.strip():
        raise InvalidCourseSlug("slug must not contain leading or trailing whitespace")
    if len(normalized) < SLUG_MIN_LENGTH or len(normalized) > SLUG_MAX_LENGTH:
        raise InvalidCourseSlug(
            f"slug length must be {SLUG_MIN_LENGTH}-{SLUG_MAX_LENGTH} characters"
        )
    if not _SLUG_PATTERN.fullmatch(normalized):
        raise InvalidCourseSlug(
            "slug must use lowercase ASCII letters, digits, and single hyphens"
        )
    words = normalized.split("-")
    if not SLUG_MIN_WORDS <= len(words) <= SLUG_MAX_WORDS:
        raise InvalidCourseSlug(
            f"slug must contain {SLUG_MIN_WORDS}-{SLUG_MAX_WORDS} words"
        )
    if any(not any("a" <= char <= "z" for char in word) for word in words):
        raise InvalidCourseSlug("every slug word must contain an English letter")
    if normalized in _RESERVED_SLUGS or normalized.startswith("temporary-course-link-"):
        raise InvalidCourseSlug("slug is reserved")
    if _BID_PATTERN.fullmatch(normalized):
        raise InvalidCourseSlug("slug must not use the legacy BID format")
    return normalized


def _parse_model_slug(raw_response: str) -> str:
    try:
        payload = json.loads(str(raw_response or ""))
    except (TypeError, json.JSONDecodeError) as exc:
        raise InvalidCourseSlug("model response must be valid JSON") from exc
    if not isinstance(payload, dict) or "slug" not in payload:
        raise InvalidCourseSlug("model response must contain the slug field")
    if not isinstance(payload["slug"], str):
        raise InvalidCourseSlug("model slug must be a string")
    return validate_course_slug(payload["slug"])


def _fallback_slug(shifu_bid: str) -> str:
    digest = hashlib.sha256(str(shifu_bid).encode("utf-8")).digest()
    suffix = base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:26]
    return f"temporary-course-link-{suffix}"


def _invoke_slug_model(
    app: Flask,
    *,
    shifu_bid: str,
    title: str,
    user_id: str,
    validation_feedback: str,
) -> str:
    from flaskr.api import llm

    prompt = load_prompt_template("course_slug").format(
        course_title=json.dumps(str(title or ""), ensure_ascii=False),
        validation_feedback=validation_feedback or "None. This is the first attempt.",
    )
    model = str(app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
    if not model:
        raise RuntimeError("DEFAULT_LLM_MODEL is not configured")

    trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "name": "course_slug",
            "user_id": user_id or "course-slug",
            "input": prompt,
        },
        root_span_payload={"name": "course_slug", "input": prompt},
    )
    response_text = ""
    try:
        response = llm.invoke_llm(
            app,
            user_id or "course-slug",
            span,
            model,
            prompt,
            json=True,
            stream=False,
            temperature=0,
            generation_name="course_slug",
            usage_context=UsageContext(
                user_bid=user_id or "course-slug",
                shifu_bid=shifu_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=0,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
            usage_metadata={"feature": "course_slug"},
        )
        for chunk in response:
            response_text += str(getattr(chunk, "result", "") or "")
        return response_text
    finally:
        finalize_langfuse_trace(
            trace=trace,
            root_span=span,
            trace_payload={"output": response_text or None},
            root_span_payload={"output": response_text or None},
        )


def prepare_course_slug(
    app: Flask,
    *,
    shifu_bid: str,
    title: str,
    user_id: str = "",
) -> PreparedCourseSlug:
    """Generate a valid base before callers stage any course mutations."""

    validation_feedback = ""
    for attempt in range(1, SLUG_GENERATION_ATTEMPTS + 1):
        try:
            raw_response = _invoke_slug_model(
                app,
                shifu_bid=shifu_bid,
                title=title,
                user_id=user_id,
                validation_feedback=validation_feedback,
            )
            return PreparedCourseSlug(
                base_slug=_parse_model_slug(raw_response),
                generation_source="llm",
            )
        except Exception as exc:
            validation_feedback = str(exc) or type(exc).__name__
            app.logger.warning(
                "Course slug generation attempt %s/%s failed for %s: %s",
                attempt,
                SLUG_GENERATION_ATTEMPTS,
                shifu_bid,
                validation_feedback,
            )

    return PreparedCourseSlug(
        base_slug=_fallback_slug(shifu_bid),
        generation_source="fallback",
    )


def _bid_exists(identifier: str) -> bool:
    return bool(
        db.session.query(DraftShifu.id)
        .filter(DraftShifu.shifu_bid == identifier)
        .first()
        or db.session.query(PublishedShifu.id)
        .filter(PublishedShifu.shifu_bid == identifier)
        .first()
    )


def assert_shifu_bid_available(shifu_bid: str) -> None:
    """Reject a new BID that is already owned by a public slug."""

    normalized = str(shifu_bid or "").strip()
    reservation = ShifuPublicIdentifier.query.filter_by(identifier=normalized).first()
    if reservation and not (
        reservation.identifier_type == "bid"
        and str(reservation.shifu_bid) == normalized
    ):
        raise ShifuIdentifierConflict(
            f"shifu_bid conflicts with the public identifier for {reservation.shifu_bid}"
        )
    conflict = ShifuCourseSlug.query.filter(
        ShifuCourseSlug.slug == normalized,
        ShifuCourseSlug.shifu_bid != normalized,
    ).first()
    if conflict:
        raise ShifuIdentifierConflict(
            f"shifu_bid conflicts with the public slug for {conflict.shifu_bid}"
        )


def _public_identifier_query(identifier: str):
    return ShifuPublicIdentifier.query.filter_by(identifier=identifier)


def _reserve_public_identifier(
    *,
    identifier: str,
    shifu_bid: str,
    identifier_type: str,
    require_new: bool = False,
    prefer_committed_bid: bool = False,
) -> ShifuPublicIdentifier:
    """Reserve one identifier with a unique-key wait safe under MySQL isolation."""

    existing = _public_identifier_query(identifier).first()
    if existing:
        if (
            str(existing.shifu_bid) == shifu_bid
            and str(existing.identifier_type) == identifier_type
        ):
            if require_new:
                raise ShifuIdentifierConflict(
                    f"public identifier is already reserved for {existing.shifu_bid}"
                )
            return existing
        if prefer_committed_bid:
            existing.shifu_bid = shifu_bid
            existing.identifier_type = "bid"
            db.session.flush()
            return existing
        raise ShifuIdentifierConflict(
            f"public identifier is already reserved for {existing.shifu_bid}"
        )

    reservation = ShifuPublicIdentifier(
        identifier=identifier,
        shifu_bid=shifu_bid,
        identifier_type=identifier_type,
    )
    _ensure_outer_transaction_for_savepoint()
    try:
        with db.session.begin_nested():
            db.session.add(reservation)
            db.session.flush()
        return reservation
    except IntegrityError as exc:
        winner = _public_identifier_query(identifier).with_for_update().first()
        if winner and (
            str(winner.shifu_bid) == shifu_bid
            and str(winner.identifier_type) == identifier_type
        ):
            if require_new:
                raise ShifuIdentifierConflict(
                    f"public identifier is already reserved for {winner.shifu_bid}"
                ) from exc
            return winner
        if winner and prefer_committed_bid:
            winner.shifu_bid = shifu_bid
            winner.identifier_type = "bid"
            db.session.flush()
            return winner
        owner = str(winner.shifu_bid) if winner else "another course"
        raise ShifuIdentifierConflict(
            f"public identifier is already reserved for {owner}"
        ) from exc


def _reserve_committed_course_bid(shifu_bid: str) -> ShifuPublicIdentifier:
    """Reserve an existing BID with precedence over any shadowed legacy slug."""

    normalized = str(shifu_bid or "").strip()
    if not _bid_exists(normalized):
        raise RuntimeError(f"cannot reserve unknown committed BID {normalized}")
    return _reserve_public_identifier(
        identifier=normalized,
        shifu_bid=normalized,
        identifier_type="bid",
        prefer_committed_bid=True,
    )


def _reserve_course_bid(
    shifu_bid: str,
    *,
    claim_new_bid: bool = False,
) -> ShifuPublicIdentifier:
    normalized = str(shifu_bid or "").strip()
    if _bid_exists(normalized):
        if claim_new_bid:
            raise ShifuIdentifierConflict(f"shifu_bid already exists: {normalized}")
        return _reserve_committed_course_bid(normalized)
    assert_shifu_bid_available(normalized)
    return _reserve_public_identifier(
        identifier=normalized,
        shifu_bid=normalized,
        identifier_type="bid",
        require_new=claim_new_bid,
    )


def _reserve_existing_course_identifiers(shifu_bid: str) -> None:
    """Reconcile one existing BID plus all current and historical slug aliases."""

    normalized_bid = str(shifu_bid or "").strip()
    _reserve_course_bid(normalized_bid)
    bindings = ShifuCourseSlug.query.filter_by(shifu_bid=normalized_bid).order_by(
        ShifuCourseSlug.version.asc()
    )
    for binding in bindings.all():
        slug = str(binding.slug)
        if _bid_exists(slug):
            # Legacy BIDs always win resolution. Reserve that committed BID and
            # leave the shadowed slug represented only by its historical binding.
            _reserve_committed_course_bid(slug)
            continue
        _reserve_public_identifier(
            identifier=slug,
            shifu_bid=normalized_bid,
            identifier_type="slug",
        )


def _current_slug_query(shifu_bid: str):
    return ShifuCourseSlug.query.filter_by(
        shifu_bid=str(shifu_bid or "").strip(),
        is_current=1,
    )


def get_shifu_slug(shifu_bid: str) -> str | None:
    normalized = str(shifu_bid or "").strip()
    if not normalized:
        return None
    try:
        binding = _current_slug_query(normalized).first()
    except RuntimeError as exc:
        # A few URL-builder unit tests intentionally use a bare Flask app with
        # no SQLAlchemy registration. Preserve the documented legacy-BID
        # fallback in that read-only environment without masking real DB errors.
        if "not registered with this 'SQLAlchemy' instance" not in str(exc):
            raise
        return None
    return str(binding.slug) if binding else None


def get_shifu_slug_map(shifu_bids: Iterable[str]) -> dict[str, str]:
    normalized_bids = {str(shifu_bid or "").strip() for shifu_bid in shifu_bids}
    normalized_bids.discard("")
    if not normalized_bids:
        return {}
    rows = ShifuCourseSlug.query.filter(
        ShifuCourseSlug.shifu_bid.in_(normalized_bids),
        ShifuCourseSlug.is_current == 1,
    ).all()
    return {str(row.shifu_bid): str(row.slug) for row in rows}


def build_course_public_path(shifu_bid: str, preview: bool = False) -> str:
    identifier = get_shifu_slug(shifu_bid) or str(shifu_bid or "").strip()
    path = f"/c/{identifier}"
    return f"{path}?preview=true" if preview else path


def resolve_shifu_identifier(app: Flask, identifier: str) -> str | None:
    """Resolve a legacy BID first, then a public slug, to the canonical BID."""

    normalized = str(identifier or "").strip()
    if not normalized:
        return None
    with _app_context_if_needed(app):
        if _bid_exists(normalized):
            return normalized
        binding = ShifuCourseSlug.query.filter_by(slug=normalized.lower()).first()
        return str(binding.shifu_bid) if binding else None


def _stable_suffix(shifu_bid: str, length: int) -> str:
    digest = hashlib.sha256(str(shifu_bid).encode("utf-8")).hexdigest()
    return digest[:length]


def _candidate_with_suffix(base_slug: str, suffix: str) -> str:
    max_base_length = SLUG_MAX_LENGTH - len(suffix) - 1
    if len(base_slug) <= max_base_length:
        shortened_base = base_slug
    else:
        source_words = base_slug.split("-")[:SLUG_MIN_WORDS]
        character_budget = max_base_length - (SLUG_MIN_WORDS - 1)
        kept_lengths = [1] * SLUG_MIN_WORDS
        character_budget -= SLUG_MIN_WORDS
        while character_budget > 0:
            extended = False
            for index, word in enumerate(source_words):
                if kept_lengths[index] >= len(word):
                    continue
                kept_lengths[index] += 1
                character_budget -= 1
                extended = True
                if character_budget == 0:
                    break
            if not extended:
                break
        shortened_base = "-".join(
            word[: kept_lengths[index]] for index, word in enumerate(source_words)
        )
    return f"{shortened_base}-{suffix}"


def _candidate_is_available(candidate: str) -> bool:
    if _public_identifier_query(candidate).first():
        return False
    slug_owner = ShifuCourseSlug.query.filter_by(slug=candidate).first()
    if slug_owner:
        return False
    return not _bid_exists(candidate)


def _ensure_outer_transaction_for_savepoint() -> None:
    """Make SQLite SAVEPOINT behavior match transactional production databases."""

    connection = db.session.connection()
    if connection.dialect.name != "sqlite":
        return
    raw_connection = getattr(connection.connection, "driver_connection", None)
    if raw_connection is not None and not raw_connection.in_transaction:
        # Python 3.11 sqlite3 legacy transaction mode does not emit BEGIN for
        # SELECT, so a first SAVEPOINT would otherwise become the outermost
        # transaction and RELEASE would survive a later session rollback.
        connection.exec_driver_sql("BEGIN")


def _release_read_transaction_before_generation() -> None:
    """Release read-only DB resources before the external model request."""

    session = db.session()
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "course slug generation must run before staging database writes"
        )
    if session.in_transaction():
        session.rollback()


def _next_slug_version(shifu_bid: str) -> int:
    query = ShifuCourseSlug.query.filter_by(shifu_bid=shifu_bid).order_by(
        ShifuCourseSlug.version.desc()
    )
    latest = query.first()
    if latest is None:
        # Avoid a MySQL next-key lock on the empty BID range. Initial-version
        # races are resolved by the version/current unique keys below.
        return 1
    latest = query.with_for_update().first()
    return int(latest.version) + 1 if latest else 1


def _is_retryable_mysql_operational_error(exc: OperationalError) -> bool:
    bind = db.session.get_bind()
    if bind.dialect.name != "mysql":
        return False
    original_args = getattr(exc.orig, "args", ())
    if not original_args:
        return False
    error_code = original_args[0]
    if error_code in _MYSQL_RETRYABLE_TRANSACTION_ERRORS:
        return True
    # InnoDB rolls back the full transaction on a deadlock. SQLAlchemy then
    # attempts to roll back the nested allocation savepoint and surfaces 1305
    # instead of the original 1213. Retrying is safe because the caller has no
    # staged course writes and allocate_course_slug rolls back the whole session.
    return (
        error_code == _MYSQL_MISSING_SAVEPOINT_ERROR
        and "SAVEPOINT" in str(exc.orig).upper()
    )


def _allocate_course_slug_once(
    *,
    shifu_bid: str,
    prepared: PreparedCourseSlug,
    claim_new_bid: bool,
) -> SlugAllocation:
    existing = _current_slug_query(shifu_bid).first()
    if existing:
        if claim_new_bid:
            raise ShifuIdentifierConflict(f"shifu_bid already exists: {shifu_bid}")
        _reserve_existing_course_identifiers(shifu_bid)
        return SlugAllocation(existing, created=False, collided=False)
    _reserve_course_bid(shifu_bid, claim_new_bid=claim_new_bid)

    candidates = [prepared.base_slug]
    candidates.extend(
        _candidate_with_suffix(
            prepared.base_slug,
            _stable_suffix(shifu_bid, suffix_length),
        )
        for suffix_length in range(8, 27, 2)
    )
    _ensure_outer_transaction_for_savepoint()
    next_version = _next_slug_version(shifu_bid)

    for index, candidate in enumerate(candidates):
        if not _candidate_is_available(candidate):
            continue
        binding = ShifuCourseSlug(
            shifu_bid=shifu_bid,
            slug=candidate,
            version=next_version,
            is_current=1,
            generation_source=prepared.generation_source,
        )
        reservation = ShifuPublicIdentifier(
            identifier=candidate,
            shifu_bid=shifu_bid,
            identifier_type="slug",
        )
        try:
            with db.session.begin_nested():
                db.session.add_all([reservation, binding])
                db.session.flush()
            return SlugAllocation(binding, created=True, collided=index > 0)
        except IntegrityError:
            # MySQL's default REPEATABLE READ would let a normal SELECT reuse
            # the pre-conflict snapshot. A locking read is a current read, so
            # after the unique-key wait resolves it can see a committed BID
            # winner and return the current binding.
            existing = _current_slug_query(shifu_bid).with_for_update().first()
            if existing:
                if claim_new_bid:
                    raise ShifuIdentifierConflict(
                        f"shifu_bid already exists: {shifu_bid}"
                    )
                return SlugAllocation(
                    existing,
                    created=False,
                    collided=str(existing.slug) != prepared.base_slug,
                )
            next_version = _next_slug_version(shifu_bid)
            continue

    raise RuntimeError(f"unable to allocate a unique course slug for {shifu_bid}")


def allocate_course_slug(
    app: Flask,
    *,
    shifu_bid: str,
    prepared: PreparedCourseSlug,
    claim_new_bid: bool = False,
) -> SlugAllocation:
    """Atomically bind a prepared base while preserving global namespace rules."""

    normalized_bid = str(shifu_bid or "").strip()
    session = db.session()
    retry_safe = not (session.new or session.dirty or session.deleted)
    for attempt in range(1, SLUG_ALLOCATION_TRANSACTION_ATTEMPTS + 1):
        try:
            return _allocate_course_slug_once(
                shifu_bid=normalized_bid,
                prepared=prepared,
                claim_new_bid=claim_new_bid,
            )
        except OperationalError as exc:
            if (
                not retry_safe
                or not _is_retryable_mysql_operational_error(exc)
                or attempt == SLUG_ALLOCATION_TRANSACTION_ATTEMPTS
            ):
                raise
            session.rollback()
            app.logger.warning(
                "Retrying course slug allocation transaction %s/%s for %s: %s",
                attempt + 1,
                SLUG_ALLOCATION_TRANSACTION_ATTEMPTS,
                normalized_bid,
                exc,
            )

    raise RuntimeError(f"unable to allocate a unique course slug for {normalized_bid}")


def ensure_shifu_slug(
    app: Flask,
    *,
    shifu_bid: str,
    title: str,
    user_id: str = "",
    claim_new_bid: bool = False,
) -> ShifuCourseSlug:
    """Return the current binding or generate and allocate the first version."""

    if not has_app_context() or current_app._get_current_object() is not app:
        raise RuntimeError("ensure_shifu_slug requires the caller's app context")
    with db.session.no_autoflush:
        existing = _current_slug_query(shifu_bid).first()
    if existing:
        if claim_new_bid:
            raise ShifuIdentifierConflict(f"shifu_bid already exists: {shifu_bid}")
        _reserve_existing_course_identifiers(str(existing.shifu_bid))
        return existing
    if claim_new_bid:
        normalized_bid = str(shifu_bid or "").strip()
        if (
            _bid_exists(normalized_bid)
            or _public_identifier_query(normalized_bid).first()
        ):
            raise ShifuIdentifierConflict(f"shifu_bid already exists: {normalized_bid}")
        assert_shifu_bid_available(normalized_bid)
    _release_read_transaction_before_generation()
    prepared = prepare_course_slug(
        app,
        shifu_bid=shifu_bid,
        title=title,
        user_id=user_id,
    )
    return allocate_course_slug(
        app,
        shifu_bid=shifu_bid,
        prepared=prepared,
        claim_new_bid=claim_new_bid,
    ).binding


def _load_latest_active_title_map(model, shifu_bids: Iterable[str]) -> dict[str, str]:
    normalized_bids = {str(shifu_bid or "").strip() for shifu_bid in shifu_bids}
    normalized_bids.discard("")
    if not normalized_bids:
        return {}
    latest_ids = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            func.max(model.id).label("latest_id"),
        )
        .filter(
            model.shifu_bid.in_(normalized_bids),
            model.deleted == 0,
        )
        .group_by(model.shifu_bid)
        .subquery()
    )
    rows = (
        db.session.query(model.shifu_bid, model.title)
        .join(
            latest_ids,
            and_(
                model.shifu_bid == latest_ids.c.shifu_bid,
                model.id == latest_ids.c.latest_id,
            ),
        )
        .all()
    )
    return {
        str(row.shifu_bid): str(row.title).strip()
        for row in rows
        if str(row.title or "").strip()
    }


def _load_backfill_title_map(shifu_bids: Iterable[str]) -> dict[str, str]:
    normalized_bids = {str(shifu_bid or "").strip() for shifu_bid in shifu_bids}
    normalized_bids.discard("")
    published_titles = _load_latest_active_title_map(
        PublishedShifu,
        normalized_bids,
    )
    draft_titles = _load_latest_active_title_map(DraftShifu, normalized_bids)
    return {
        course_bid: published_titles.get(course_bid) or draft_titles.get(course_bid, "")
        for course_bid in normalized_bids
    }


def _load_active_shifu_bid_page(*, after_bid: str, batch_size: int) -> list[str]:
    """Load one stable keyset page without materializing every course BID."""

    draft_bids = db.session.query(DraftShifu.shifu_bid.label("shifu_bid")).filter(
        DraftShifu.deleted == 0
    )
    published_bids = db.session.query(
        PublishedShifu.shifu_bid.label("shifu_bid")
    ).filter(PublishedShifu.deleted == 0)
    active_bids = draft_bids.union(published_bids).subquery()
    query = db.session.query(active_bids.c.shifu_bid)
    if after_bid:
        query = query.filter(active_bids.c.shifu_bid > after_bid)
    rows = query.order_by(active_bids.c.shifu_bid.asc()).limit(batch_size).all()
    return [str(row[0]) for row in rows if row and row[0]]


def _iter_active_shifu_bid_batches(
    *, batch_size: int, shifu_bid: str = ""
) -> Iterable[list[str]]:
    if shifu_bid:
        if _bid_exists(shifu_bid):
            yield [shifu_bid]
        return

    after_bid = ""
    while True:
        batch = _load_active_shifu_bid_page(
            after_bid=after_bid,
            batch_size=batch_size,
        )
        if not batch:
            return
        yield batch
        after_bid = batch[-1]


def backfill_course_slugs(
    app: Flask,
    *,
    dry_run: bool = False,
    batch_size: int = 100,
    shifu_bid: str = "",
) -> dict[str, int | bool]:
    """Backfill missing bindings one commit at a time so reruns are safe."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    normalized_bid = str(shifu_bid or "").strip()
    stats: dict[str, int | bool] = {
        "dry_run": bool(dry_run),
        "scanned": 0,
        "existing": 0,
        "created": 0,
        "llm": 0,
        "fallback": 0,
        "collision": 0,
        "failed": 0,
        "missing": 0,
    }
    with _app_context_if_needed(app):
        for batch in _iter_active_shifu_bid_batches(
            batch_size=batch_size,
            shifu_bid=normalized_bid,
        ):
            existing_slugs = get_shifu_slug_map(batch)
            missing_bids: list[str] = []
            for course_bid in batch:
                stats["scanned"] = int(stats["scanned"]) + 1
                if course_bid in existing_slugs:
                    stats["existing"] = int(stats["existing"]) + 1
                    if not dry_run:
                        try:
                            _reserve_existing_course_identifiers(course_bid)
                            db.session.commit()
                        except Exception as exc:
                            db.session.rollback()
                            stats["failed"] = int(stats["failed"]) + 1
                            app.logger.error(
                                "Course identifier reconciliation failed for %s: %s",
                                course_bid,
                                exc,
                                exc_info=True,
                            )
                    continue
                stats["missing"] = int(stats["missing"]) + 1
                missing_bids.append(course_bid)
            if dry_run or not missing_bids:
                continue
            titles = _load_backfill_title_map(missing_bids)
            _release_read_transaction_before_generation()
            for course_bid in missing_bids:
                title = titles.get(course_bid, "")
                try:
                    prepared = (
                        prepare_course_slug(
                            app,
                            shifu_bid=course_bid,
                            title=title,
                            user_id="course-slug-backfill",
                        )
                        if title
                        else PreparedCourseSlug(
                            base_slug=_fallback_slug(course_bid),
                            generation_source="fallback",
                        )
                    )
                    allocation = allocate_course_slug(
                        app,
                        shifu_bid=course_bid,
                        prepared=prepared,
                    )
                    _reserve_existing_course_identifiers(course_bid)
                    source = str(allocation.binding.generation_source)
                    collided = allocation.collided
                    db.session.commit()
                    stats["missing"] = max(0, int(stats["missing"]) - 1)
                    stats["created"] = int(stats["created"]) + int(allocation.created)
                    if source in {"llm", "fallback"}:
                        stats[source] = int(stats[source]) + 1
                    if collided:
                        stats["collision"] = int(stats["collision"]) + 1
                except Exception as exc:
                    db.session.rollback()
                    stats["failed"] = int(stats["failed"]) + 1
                    app.logger.error(
                        "Course slug backfill failed for %s: %s",
                        course_bid,
                        exc,
                        exc_info=True,
                    )
    return stats
