from sqlalchemy import (
    Column,
    DateTime,
    String,
    Integer,
    TIMESTAMP,
    Text,
    Numeric,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func


from ...dao import db


# active model
class Active(db.Model):
    __tablename__ = "active"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    active_id = Column(String(36), nullable=False, default="", comment="Active UUID")
    active_name = Column(String(255), nullable=False, default="", comment="Active name")
    active_desc = Column(Text, nullable=False, default="", comment="Active description")
    active_type = Column(Integer, nullable=False, default=0, comment="Active type")
    active_join_type = Column(
        Integer, nullable=False, default=0, comment="Active join type"
    )
    active_status = Column(
        Integer, nullable=False, default=0, index=True, comment="Active status"
    )
    active_start_time = Column(
        DateTime,
        nullable=False,
        index=True,
        default=func.now(),
        comment="Active start time",
    )
    active_end_time = Column(
        DateTime,
        nullable=False,
        index=True,
        default=func.now(),
        comment="Active end time",
    )
    active_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Active price"
    )
    active_discount = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Active discount"
    )
    active_discount_type = Column(
        Integer, nullable=False, default=0, comment="Active discount type"
    )
    active_discount_desc = Column(
        Text, nullable=False, default="", comment="Active discount description"
    )
    active_filter = Column(Text, nullable=False, default="", comment="Active filter")
    active_course = Column(
        String(36), nullable=False, default="", comment="Active course"
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


class ActiveUserRecord(db.Model):
    __tablename__ = "active_user_record"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    record_id = Column(String(36), nullable=False, default="", comment="Record UUID")
    active_id = Column(String(36), nullable=False, default="", comment="Active UUID")
    active_name = Column(String(255), nullable=False, default="", comment="Active name")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Price of the active"
    )

    order_id = Column(String(36), nullable=False, default="", comment="Order UUID")
    status = Column(Integer, nullable=False, default=0, comment="Status of the record")
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
