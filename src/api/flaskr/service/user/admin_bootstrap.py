"""Bootstrap the administrator account of an installation.

Signing in never grants the operator role: being the first account is not proof
of owning the deployment. Instead, an installation without any operator gets an
``admin`` username account with a random password. It receives the operator and
creator roles and, when the installation holds exactly one course, ownership of
that bundled demo course. The password is returned once for the caller to show
the person running the command.
"""

from __future__ import annotations

import contextlib
import secrets
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import cache
from flaskr.common.config import get_redis_key_prefix
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import UserInfo
from flaskr.service.user.operator_account_creation import (
    create_operator_password_account,
)
from flaskr.service.user.password_utils import validate_password_strength
from flaskr.service.user.repository import mark_user_roles
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    mark_creator_role_if_needed,
    run_creator_granted_post_auth,
)

if TYPE_CHECKING:
    from flask import Flask

BOOTSTRAP_ADMIN_USERNAME = "admin"
BOOTSTRAP_ADMIN_NICKNAME = "Admin"
BOOTSTRAP_OPERATOR_USER_BID = "system-bootstrap"
BOOTSTRAP_POST_AUTH_SOURCE = "bootstrap_admin"
BOOTSTRAP_PASSWORD_LENGTH = 20
REASON_CONFIG_REJECTED = "invalid_configured_password"
# Owner recorded by ``flask console update_demo_shifu`` for imported demos.
DEMO_COURSE_OWNERS = frozenset({"", "system"})
_LOCK_TIMEOUT_SECONDS = 60
_LOCK_WAIT_SECONDS = 10
_PASSWORD_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True)
class BootstrapAdminResult:
    """Outcome of an admin bootstrap attempt."""

    created: bool
    reason: str
    username: str = ""
    # Empty when the password came from BOOTSTRAP_ADMIN_PASSWORD.
    password: str = ""
    password_from_config: bool = False


def generate_bootstrap_password(length: int = BOOTSTRAP_PASSWORD_LENGTH) -> str:
    """Return a random password with at least one letter and one digit."""
    while True:
        password = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if any(char.isalpha() for char in password) and any(
            char.isdigit() for char in password
        ):
            return password


def _has_operator() -> bool:
    return (
        UserInfo.query.filter(
            UserInfo.deleted == 0,
            UserInfo.is_operator == 1,
        ).first()
        is not None
    )


def _is_acceptable_password(password: str) -> bool:
    try:
        validate_password_strength(password)
    except AppError:
        return False
    return True


def _assign_single_demo_course(user_bid: str) -> None:
    """Give the admin the bundled demo course when it is the only course.

    A course counts once whether it has a published record, a draft record or
    both. Only a course whose records are all still owned by the demo importer
    moves, so a course a teacher authored is never taken over.
    """
    records: list[PublishedShifu | DraftShifu] = [
        *PublishedShifu.query.filter(PublishedShifu.deleted == 0).all(),
        *DraftShifu.query.filter(DraftShifu.deleted == 0).all(),
    ]
    if len({record.shifu_bid for record in records}) != 1:
        return
    if any(
        (record.created_user_bid or "") not in DEMO_COURSE_OWNERS for record in records
    ):
        return
    # Permission checks read the owner from both the published and draft records.
    for record in records:
        record.created_user_bid = user_bid
    db.session.flush()


def _grant_bootstrap_admin_roles(app: Flask, user_bid: str) -> bool:
    """Make ``user_bid`` an operator and creator; return whether creator is new.

    Runs inside the caller's unit of work.
    """
    creator_granted_now = mark_creator_role_if_needed(user_bid)
    mark_user_roles(user_bid, is_operator=True)
    # The demo import ran before this account existed, so it could not grant
    # the demos to it; grant them now, whether or not ownership moves below.
    ensure_demo_course_permissions(app, user_bid)
    _assign_single_demo_course(user_bid)
    return creator_granted_now


def bootstrap_admin_account(app: Flask) -> BootstrapAdminResult:
    """Create the ``admin`` account when the installation has no operator."""
    # Serialize concurrent container starts across the check and the commit.
    lock = cache.lock(
        f"{get_redis_key_prefix(app)}bootstrap_admin",
        timeout=_LOCK_TIMEOUT_SECONDS,
        blocking_timeout=_LOCK_WAIT_SECONDS,
    )
    if not lock.acquire(blocking=True, blocking_timeout=_LOCK_WAIT_SECONDS):
        return BootstrapAdminResult(created=False, reason="busy")
    configured_password = str(app.config.get("BOOTSTRAP_ADMIN_PASSWORD") or "")
    try:
        password = configured_password or generate_bootstrap_password()
        # One transaction: an account is never left without its roles, so a
        # failed run is retried on the next start instead of being skipped.
        with app_context_scope(app), unit_of_work():
            if _has_operator():
                return BootstrapAdminResult(created=False, reason="operator_exists")
            # Report a rejected configured password by name; the value is a
            # secret, so the error raised by the strength check is not shown.
            if configured_password and not _is_acceptable_password(configured_password):
                return BootstrapAdminResult(
                    created=False, reason=REASON_CONFIG_REJECTED
                )
            try:
                created = create_operator_password_account(
                    app,
                    operator_user_bid=BOOTSTRAP_OPERATOR_USER_BID,
                    username=BOOTSTRAP_ADMIN_USERNAME,
                    password=password,
                    nickname=BOOTSTRAP_ADMIN_NICKNAME,
                )
            except AppError as error:
                if error.code == ERROR_CODE["server.user.usernameAlreadyRegistered"]:
                    return BootstrapAdminResult(created=False, reason="username_taken")
                raise
            user_bid = created["user_bid"]
            creator_granted_now = _grant_bootstrap_admin_roles(app, user_bid)
    finally:
        # An expired lock must not turn a committed creation into a failure.
        with contextlib.suppress(Exception):
            lock.release()

    if creator_granted_now:
        # Same follow-up as any other creator grant, such as trial credits.
        run_creator_granted_post_auth(
            app,
            user_id=user_bid,
            source=BOOTSTRAP_POST_AUTH_SOURCE,
            login_context="admin",
            created_new_user=True,
        )

    app.logger.info(
        "security_event=bootstrap_admin_created target_user_bid=%s", user_bid
    )
    return BootstrapAdminResult(
        created=True,
        reason="created",
        username=created["username"],
        # Never echo back a configured secret.
        password="" if configured_password else password,
        password_from_config=bool(configured_password),
    )
