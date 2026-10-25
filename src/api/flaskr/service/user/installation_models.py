"""Durable installation ownership and local administrator bindings."""

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from sqlalchemy import CheckConstraint, Column, DateTime, Integer, SmallInteger, String


class InstallationState(db.Model):
    """Own the one-time transition from fresh installation to administrator."""

    __tablename__ = "user_installation_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_user_installation_singleton"),
        CheckConstraint(
            "mode IN ('legacy', 'managed')", name="ck_user_installation_mode"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=False)
    mode = Column(String(16), nullable=False)
    initialized_at = Column(DateTime, nullable=True)
    initialized_user_bid = Column(String(32), nullable=False, default="")
    token_digest = Column(String(64), nullable=False, default="")
    token_expires_at = Column(DateTime, nullable=True)
    token_origin = Column(String(255), nullable=False, default="")
    claim_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)


class LocalAdminAccount(db.Model):
    """Bind a unique local username to its user and password credential."""

    __tablename__ = "user_local_admin_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    user_bid = Column(String(32), nullable=False, unique=True)
    credential_bid = Column(String(32), nullable=False, unique=True)
    deleted = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)
