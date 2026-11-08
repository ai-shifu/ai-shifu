"""Resolve legacy bindings within one learner and course."""

from hashlib import sha256

from flaskr.dao import db
from flaskr.service.memory.course_references import is_course_reference
from flaskr.service.memory.models import CourseAnswerAlias
from flaskr.service.profile.api import get_global_profile_keys
from flaskr.service.profile.models import VariableValue
from sqlalchemy import LargeBinary, cast, func, select


def _is_course_key(key: str) -> bool:
    return (
        bool(key)
        and not key.startswith("sys_")
        and not is_course_reference(key)
        and key not in get_global_profile_keys()
    )


def load_course_answer_aliases(user_bid: str, shifu_bid: str) -> dict[str, str]:
    """Read bindings, including those whose answer was deleted."""
    if not shifu_bid:
        return {}
    rows = db.session.scalars(
        select(CourseAnswerAlias).filter_by(user_bid=user_bid, shifu_bid=shifu_bid)
    )
    return {row.alias: row.question_key for row in rows}


def load_course_alias_targets(
    user_bid: str, shifu_bid: str, question_keys: set[str]
) -> dict[str, str]:
    """Read exact live answers that may fall outside the supplementary memory budget."""
    question_keys = {key for key in question_keys if _is_course_key(key)}
    if not shifu_bid or not question_keys:
        return {}
    exact_key = cast(VariableValue.key, LargeBinary)
    live_ids = (
        select(func.max(VariableValue.id))
        .where(
            VariableValue.user_bid == user_bid,
            VariableValue.shifu_bid == shifu_bid,
            VariableValue.deleted == 0,
            exact_key.in_([key.encode("utf-8") for key in question_keys]),
        )
        .group_by(exact_key)
    )
    rows = db.session.execute(
        select(VariableValue.key, VariableValue.value).where(
            VariableValue.id.in_(live_ids)
        )
    )
    return {row.key: row.value for row in rows}


def stage_course_answer_alias(
    user_bid: str, shifu_bid: str, alias: str, question_key: str
) -> None:
    """Stage the latest mapping in the same transaction as its accepted answer."""
    if (
        not shifu_bid
        or alias == question_key
        or not _is_course_key(alias)
        or not _is_course_key(question_key)
    ):
        return
    digest = sha256(alias.encode("utf-8")).hexdigest()
    row = db.session.get(
        CourseAnswerAlias, (user_bid, shifu_bid, digest), with_for_update=True
    )
    if row is None:
        db.session.add(
            CourseAnswerAlias(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                alias_digest=digest,
                alias=alias,
                question_key=question_key,
            )
        )
    else:
        row.question_key = question_key


def retire_course_answer_alias(user_bid: str, shifu_bid: str, key: str) -> None:
    """Give a newly answered question precedence over a former alias of that text."""
    if not shifu_bid or not _is_course_key(key):
        return
    digest = sha256(key.encode("utf-8")).hexdigest()
    row = db.session.get(
        CourseAnswerAlias, (user_bid, shifu_bid, digest), with_for_update=True
    )
    if row is not None:
        db.session.delete(row)
