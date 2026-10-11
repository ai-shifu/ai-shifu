"""Compare taught lesson sources without loading stored conversation histories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem
from sqlalchemy import (
    LargeBinary,
    and_,
    case,
    cast,
    func,
    literal_column,
    select,
    true,
    tuple_,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import ColumnElement


@dataclass(frozen=True)
class LessonContentState:
    """Describe a recognizable teaching baseline for one scoped lesson attempt."""

    started: bool = False
    finished: bool = False
    has_content_update: bool = False


def _normalize_content(content: str) -> str:
    """Ignore platform line endings, preserving every other authored character."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def lesson_content_state_from_document(
    *,
    row: LearnAgentSession | None,
    document: object,
    current_content: str,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> LessonContentState:
    """Compare an already parsed preview document without loading the engine.

    A reserved preview row and an unsuccessful start have no teaching history.
    Conversely, a persisted interrupted turn can have messages while its turn
    counter remains zero. Only a nonempty message array establishes teaching.
    """
    if (
        row is None
        or row.user_bid != user_bid
        or row.shifu_bid != shifu_bid
        or row.outline_item_bid != outline_bid
        or row.active_key
        != active_key_for(user_bid, outline_bid, preview_mode=preview_mode)
        or row.deleted != 0
        or row.schema_version != AGENT_SESSION_SCHEMA_VERSION
        or not isinstance(document, dict)
        or not isinstance(current_content, str)
    ):
        return LessonContentState()
    script = document.get("script")
    messages = document.get("messages")
    if (
        not isinstance(script, dict)
        or not isinstance(script.get("script"), str)
        or not isinstance(messages, list)
        or not messages
    ):
        return LessonContentState()
    return LessonContentState(
        started=True,
        finished=row.finished == 1,
        has_content_update=(
            _normalize_content(script["script"]) != _normalize_content(current_content)
        ),
    )


def _normalized_sql_content(content: ColumnElement) -> ColumnElement:
    return func.replace(func.replace(content, "\r\n", "\n"), "\r", "\n")


def _lesson_content_state_query(
    *,
    user_bid: str,
    shifu_bid: str,
    preview_mode: bool,
    outline_ids: Mapping[str, int],
    dialect_name: str,
    mysql_json_table: bool = True,
) -> Select:
    """Project only identifiers and booleans from indexed current-session rows."""
    session = LearnAgentSession.__table__.c
    outline_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    outline = outline_model.__table__.c
    # Guard the input to every JSON function, rather than relying on WHERE/AND
    # evaluation order: an optimizer may evaluate extraction before validation.
    document = case(
        (func.json_valid(session.session_data) == 1, session.session_data),
        else_="{}",
    )
    source = func.json_extract(document, "$.script.script")
    snapshot = None
    if dialect_name == "mysql" and mysql_json_table:
        # Materialize native JSON values once. Repeating JSON_EXTRACT against
        # LONGTEXT reparses the whole conversation for every projected flag.
        # JSON_TABLE is supported by the project's MySQL 8.0 deployment.
        snapshot = func.json_table(
            document,
            literal_column(
                "'$' COLUMNS ("
                "source JSON PATH '$.script.script' NULL ON EMPTY NULL ON ERROR, "
                "messages_present INTEGER EXISTS PATH '$.messages[*]')"
            ),
        ).table_valued(
            "source",
            "messages_present",
            name="lesson_snapshot",
            joins_implicitly=True,
        )
        source = snapshot.c.source
    if dialect_name in {"mysql", "mariadb"}:
        is_source_string = func.json_type(source) == "STRING"
        if snapshot is not None:
            # [*] matches array elements only; [0] would auto-wrap a scalar or
            # object. EXISTS avoids copying the entire conversation subtree.
            has_messages = snapshot.c.messages_present == 1
        else:
            messages = func.json_extract(document, "$.messages")
            has_messages = and_(
                func.json_type(messages) == "ARRAY", func.json_length(messages) > 0
            )
        source = func.json_unquote(source)
    else:
        is_source_string = func.json_type(document, "$.script.script") == "text"
        has_messages = and_(
            func.json_type(document, "$.messages") == "array",
            func.json_array_length(document, "$.messages") > 0,
        )
    started = case(
        (and_(is_source_string, has_messages), True),
        else_=False,
    )
    # MySQL's usual text collations ignore case/accents and can ignore trailing
    # spaces. Binary values compare the normalized source exactly on both DBs.
    changed = cast(_normalized_sql_content(source), LargeBinary) != cast(
        _normalized_sql_content(outline.content), LargeBinary
    )
    query = (
        select(
            session.outline_item_bid,
            started.label("started"),
            (session.finished == 1).label("finished"),
            case((changed, True), else_=False).label("source_changed"),
        )
        .select_from(LearnAgentSession.__table__)
        .join(
            outline_model.__table__,
            and_(
                outline.outline_item_bid == session.outline_item_bid,
                outline.shifu_bid == session.shifu_bid,
                tuple_(outline.outline_item_bid, outline.id).in_(
                    list(outline_ids.items())
                ),
                outline.deleted == 0,
                outline.hidden == 0,
            ),
        )
        .where(
            session.active_key.in_(
                [
                    active_key_for(user_bid, bid, preview_mode=preview_mode)
                    for bid in outline_ids
                ]
            ),
            session.user_bid == user_bid,
            session.shifu_bid == shifu_bid,
            tuple_(session.outline_item_bid, session.active_key).in_(
                [
                    (
                        bid,
                        active_key_for(user_bid, bid, preview_mode=preview_mode),
                    )
                    for bid in outline_ids
                ]
            ),
            session.deleted == 0,
            session.schema_version == AGENT_SESSION_SCHEMA_VERSION,
        )
    )
    if snapshot is not None:
        query = query.join(snapshot, true())
    if dialect_name == "mysql":
        # Bound the read to requested active sessions even when the learner has
        # many retired attempts. MySQL otherwise sometimes prefers user_bid.
        query = query.with_hint(
            LearnAgentSession.__table__,
            "FORCE INDEX (uq_learn_agent_sessions_active)",
            dialect_name="mysql",
        )
    return query


def load_lesson_content_states(
    *,
    user_bid: str,
    shifu_bid: str,
    preview_mode: bool,
    outline_ids: Mapping[str, int],
) -> dict[str, LessonContentState]:
    """Compare current lesson rows in one query, without transferring source text.

    The caller supplies current physical outline IDs and handles eligibility
    such as formal learner progress. Missing/retired/unrecognized sessions or
    outline rows have no trustworthy baseline and are absent from the result.
    """
    if not outline_ids:
        return {}
    dialect = db.session.get_bind().dialect
    dialect_name = "mariadb" if getattr(dialect, "is_mariadb", False) else dialect.name
    version = dialect.server_version_info
    query = _lesson_content_state_query(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        preview_mode=preview_mode,
        outline_ids=outline_ids,
        dialect_name=dialect_name,
        # Before 8.0.21 JSON_TABLE can raise on a JSON-null value despite its
        # ON ERROR clause. Unknown/older versions retain the guarded fallback.
        mysql_json_table=bool(version and version >= (8, 0, 21)),
    )
    # Apply eligibility to scalar results, so MySQL does not repeat the costly
    # JSON validation/extraction of the LONGTEXT history for each projection.
    return {
        row.outline_item_bid: LessonContentState(
            started=bool(row.started),
            finished=bool(row.started and row.finished),
            has_content_update=bool(row.started and row.source_changed),
        )
        for row in db.session.execute(query)
    }
