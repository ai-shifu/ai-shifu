"""Database publication boundary for the one onboarding configuration JSON."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

from flask import current_app
from flaskr.common.config import has_explicit_env_override
from flaskr.dao import db, uow
from flaskr.service.common.models import raise_error
from flaskr.service.config.funcs import (
    ConfigCache,
    _get_config_cache_key,
    _normalize_updated_by,
    get_config,
    has_config_override,
    redis,
)
from flaskr.service.config.models import Config
from flaskr.util import generate_id
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

CONFIG_KEY = "PROFILE_ONBOARDING_FLOW"


def assert_profile_onboarding_persistable() -> None:
    """Fail before compilation if this process cannot publish the DB value."""
    if (
        has_explicit_env_override(CONFIG_KEY)
        or has_config_override(CONFIG_KEY)
        or uow.in_unit_of_work()
    ):
        raise_error("server.profile.profileOnboardingConfigNotPersistable")


def _config_row(*, for_update: bool = False) -> Config | None:
    query = Config.query.filter(Config.key == CONFIG_KEY, Config.deleted == 0).order_by(
        Config.created_at.desc(), Config.id.desc()
    )
    if for_update:
        query = query.with_for_update()
    return query.populate_existing().first()


def read_profile_onboarding_database(app: Flask) -> str | None:
    """Use a short independent session, not a cache or an earlier read snapshot."""
    with app.app_context():
        row = _config_row()
        return row.value if row else None


def read_profile_onboarding_effective_value(app: Flask, default: str) -> str:
    """Avoid stale cache repopulation races for this versioned document only."""
    if has_explicit_env_override(CONFIG_KEY) or has_config_override(CONFIG_KEY):
        return get_config(CONFIG_KEY, default)
    return read_profile_onboarding_database(app) or default


@contextmanager
def _publication_lock() -> Iterator[None]:
    # A connection-scoped MySQL lock also serializes the first insert, for which
    # no row/unique key exists. Unlike a Redis lease it cannot expire mid-commit.
    # Keep the dedicated connection open until the publishing transaction ends.
    with db.engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT GET_LOCK(:name, 5)"),
            {"name": "ai-shifu:profile-onboarding:publish"},
        ).scalar()
        if acquired != 1:
            raise_error("server.profile.profileOnboardingConfigBusy")
        try:
            yield
        finally:
            try:
                connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"),
                    {"name": "ai-shifu:profile-onboarding:publish"},
                )
            except Exception:
                # Disconnecting releases MySQL named locks. Never turn a
                # successful commit into a reported rollback during cleanup.
                with suppress(Exception):
                    connection.invalidate()
                current_app.logger.warning("Onboarding publication lock cleanup failed")


def publish_profile_onboarding_database(
    app: Flask, *, expected_value: str | None, value: str, updated_by: str
) -> bool:
    """CAS the full JSON; return whether a committed cache refresh is pending."""
    assert_profile_onboarding_persistable()
    with app.app_context(), _publication_lock():
        with uow.unit_of_work():
            row = _config_row(for_update=True)
            if (row.value if row else None) != expected_value:
                raise_error("server.profile.profileOnboardingConfigConflict")
            if row is None:
                row = Config(config_bid=generate_id(app), key=CONFIG_KEY, deleted=0)
                db.session.add(row)
            row.value = value
            row.is_encrypted = False
            row.remark = "Profile onboarding MarkdownFlow configuration"
            row.updated_by = _normalize_updated_by(updated_by)
        # The database is durable now. Do not wrap this in the transaction or
        # report a cache exception as if the administrator's save rolled back.
        cache_key = _get_config_cache_key(app, CONFIG_KEY)
        try:
            redis.set(
                cache_key,
                ConfigCache(is_encrypted=False, value=value).model_dump_json(),
                ex=86400,
            )
        except Exception:
            app.logger.warning("Onboarding config committed; cache refresh pending")
            try:
                redis.delete(cache_key)
            except Exception:
                app.logger.warning("Onboarding config cache invalidation failed")
            return True
    return False
