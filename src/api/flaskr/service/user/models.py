from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Date,
    Text,
    Boolean,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .consts import USER_STATE_UNREGISTERED, CREDENTIAL_STATE_UNVERIFIED


class User(db.Model):
    __tablename__ = "user_info"

    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    user_id = Column(
        String(36), nullable=False, index=True, default="", comment="User UUID"
    )
    username = Column(String(255), nullable=False, default="", comment="Login username")
    name = Column(String(255), nullable=False, default="", comment="User real name")
    email = Column(String(255), nullable=False, default="", comment="Email")
    mobile = Column(
        String(20), nullable=False, index=True, default="", comment="Mobile"
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        onupdate=func.now(),
        default=func.now(),
        comment="Update time",
    )
    user_state = Column(Integer, nullable=True, default=0, comment="User_state")
    user_sex = Column(Integer, nullable=True, default=0, comment="user sex")
    user_birth = Column(Date, nullable=True, default="2003-1-1", comment="user birth")
    user_avatar = Column(String(255), nullable=True, default="", comment="user avatar")
    user_open_id = Column(
        String(255), nullable=True, index=True, default="", comment="user open id"
    )
    user_unicon_id = Column(
        String(255), nullable=True, index=True, default="", comment="user unicon id"
    )
    user_language = Column(
        String(30), nullable=True, default="en-US", comment="user language"
    )
    is_admin = Column(Boolean, nullable=False, default=False, comment="is admin")
    is_creator = Column(Boolean, nullable=False, default=False, comment="is creator")
    extra_data = Column(Text, nullable=True, default="", comment="extra_data")

    def __init__(
        self,
        user_id,
        username="",
        name="",
        email="",
        mobile="",
        user_state=0,
        language="en-US",
    ):
        self.user_id = user_id
        self.username = username
        self.name = name
        self.email = email
        self.mobile = mobile
        self.user_state = user_state
        self.user_language = language


class UserConversion(db.Model):
    __tablename__ = "user_conversion"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    conversion_id = Column(
        String(36), nullable=False, default="", comment="Conversion UUID"
    )
    conversion_source = Column(
        String(36), nullable=False, default=0, comment="Conversion type"
    )
    conversion_status = Column(
        Integer, nullable=False, default=0, comment="Conversion state"
    )
    conversion_uuid = Column(
        String(36), nullable=False, default="", comment="Conversion UUID"
    )
    conversion_third_platform = Column(
        String(255), nullable=False, default="", comment="Conversion third platform"
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )

    def __init__(
        self,
        user_id,
        conversion_id,
        conversion_source,
        conversion_status,
        conversion_uuid="",
        conversion_third_platform="",
    ):
        self.user_id = user_id
        self.conversion_id = conversion_id
        self.conversion_source = conversion_source
        self.conversion_status = conversion_status
        self.conversion_uuid = conversion_uuid
        self.conversion_third_platform = conversion_third_platform


class UserToken(db.Model):
    __tablename__ = "user_token"
    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    token = Column(String(255), nullable=False, default="", comment="Token")
    token_type = Column(Integer, nullable=False, default=0, comment="Token type")
    token_expired_at = Column(
        TIMESTAMP, nullable=True, default=func.now(), comment="Token expired time"
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class UserVerifyCode(db.Model):
    __tablename__ = "user_verify_code"
    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    phone = Column(String(36), nullable=False, default="", comment="User phone")
    mail = Column(String(36), nullable=False, default="", comment="User mail")
    verify_code = Column(String(10), nullable=False, default="", comment="Verify code")
    verify_code_type = Column(
        Integer, nullable=False, default=0, comment="Verify code type"
    )
    verify_code_send = Column(
        Integer,
        nullable=False,
        default=0,
        comment="verification code send state",
    )
    verify_code_used = Column(
        Integer,
        nullable=False,
        default=0,
        comment="verification code used state",
    )
    user_ip = Column(String(100), nullable=False, default="", comment="user ip")

    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class UserInfo(db.Model):
    __tablename__ = "user_users"

    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    # Store either phone (SMS verification) or email (email/Google verification)
    user_identify = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="User identifier: phone or email",
    )
    nickname = Column(String(255), nullable=False, default="", comment="User nickname")
    avatar = Column(String(255), nullable=False, default="", comment="User avatar")
    birthday = Column(Date, nullable=True, comment="User birthday")
    language = Column(String(30), nullable=False, default="", comment="User language")
    state = Column(
        Integer,
        nullable=False,
        default=USER_STATE_UNREGISTERED,
        comment="User state: 1101=unregistered, 1102=registered, 1103=trail, 1104=paid",
        index=True,
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
        index=True,
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )


class AuthCredential(db.Model):
    __tablename__ = "user_auth_credentials"
    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    credential_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Credential business identifier",
        index=True,
    )
    user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    provider_name = Column(
        String(255), nullable=False, default="", comment="Provider name", index=True
    )
    subject_id = Column(
        String(255), nullable=False, default="", comment="Subject id", index=True
    )
    subject_format = Column(
        String(255), nullable=False, default="", comment="Subject format", index=True
    )
    identifier = Column(
        String(255), nullable=False, default="", comment="Identifier", index=True
    )
    raw_profile = Column(Text, nullable=False, default="", comment="Raw profile")
    state = Column(
        Integer,
        nullable=False,
        default=CREDENTIAL_STATE_UNVERIFIED,
        comment="Credential state: 1201=unverified, 1202=verified",
        index=True,
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
        index=True,
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
