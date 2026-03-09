"""Data model for user API keys used for programmatic access."""

from sqlalchemy import Column, BIGINT, String, SmallInteger, DateTime, func

from flaskr.dao import db


class UserApiKey(db.Model):
    """API key entity for programmatic access by external AI tools."""

    __tablename__ = "user_api_keys"
    __table_args__ = {"comment": "User API keys for programmatic access"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    api_key_bid = Column(
        String(32),
        nullable=False,
        index=True,
        unique=True,
        comment="API key business identifier",
    )

    user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        comment="Owner user business identifier",
    )

    key_hash = Column(
        String(128),
        nullable=False,
        index=True,
        comment="SHA-256 hash of the API key",
    )

    key_prefix = Column(
        String(12),
        nullable=False,
        default="",
        comment="First 8 chars of key for display identification",
    )

    name = Column(
        String(100),
        nullable=False,
        default="",
        comment="Human-readable key name",
    )

    last_used_at = Column(
        DateTime,
        nullable=True,
        comment="Last usage timestamp",
    )

    revoked = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Revoked flag: 0=active, 1=revoked",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )
