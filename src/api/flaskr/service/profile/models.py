from sqlalchemy import Column, DateTime, SmallInteger, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from ...dao import db


PROFILE_TYPE_SYSTEM = 2801
PROFILE_TYPE_USER = 2802
PROFILE_TYPE_COURSE = 2803
PROFILE_TYPE_COURSE_SECTION = 2804
PROFILE_TYPE_TEMP = 2805


PROFILE_TYPE_INPUT_UNCONF = 2900
PROFILE_TYPE_INPUT_TEXT = 2901
PROFILE_TYPE_INPUT_NUMBER = 2902
PROFILE_TYPE_INPUT_SELECT = 2903
PROFILE_TYPE_INPUT_SEX = 2904
PROFILE_TYPE_INPUT_DATE = 2905


PROFILE_SHOW_TYPE_ALL = 3001
PROFILE_SHOW_TYPE_USER = 3002
PROFILE_SHOW_TYPE_COURSE = 3003
PROFILE_SHOW_TYPE_HIDDEN = 3004

PROFILE_CONF_TYPE_PROFILE = 3101
PROFILE_CONF_TYPE_ITEM = 3102


CONST_PROFILE_TYPE_TEXT = "text"
CONST_PROFILE_TYPE_OPTION = "option"

PROFILE_TYPE_VLUES = {
    CONST_PROFILE_TYPE_TEXT: PROFILE_TYPE_INPUT_TEXT,
    CONST_PROFILE_TYPE_OPTION: PROFILE_TYPE_INPUT_SELECT,
}


CONST_PROFILE_SCOPE_USER = "user"
CONST_PROFILE_SCOPE_SYSTEM = "system"


class Variable(db.Model):
    """
    Variable definition table for MarkdownFlow-based shifu.

    Defines variables referenced in course content (via MarkdownFlow markers) and used to
    collect learner inputs. Variables can be scoped to a specific Shifu or defined at
    system scope (empty shifu_bid). This table stores definitions only; per-user variable
    values are stored in the user variable table.
    """

    __tablename__ = "var_variables"
    __table_args__ = {
        "comment": (
            "Variable definition table for MarkdownFlow-based shifu. Defines variables "
            "referenced in course content (via MarkdownFlow markers) and used to collect "
            "learner inputs. Variables can be scoped to a specific Shifu or defined at "
            "system scope (empty shifu_bid). This table stores definitions only; per-user "
            "variable values are stored in the user variable table."
        )
    }

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    variable_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Variable business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment=(
            "Shifu business identifier (empty means system/global scope; otherwise the "
            "variable belongs to the specified Shifu)"
        ),
    )
    key = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Variable key",
    )
    is_hidden = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Hidden flag: 0=visible, 1=hidden",
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
    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )
    updated_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Last updater user business identifier",
    )


class VariableValue(db.Model):
    """
    User variable value table for variables.

    Stores the actual values entered during learning for variables defined in var_variables.
    Each record represents a user's value for a variable within a Shifu or global/system
    scope. Important: This table stores user data (values), not variable definitions.
    """

    __tablename__ = "var_variable_values"
    __table_args__ = {
        "comment": (
            "User variable value table for variables. Stores the actual values entered "
            "during learning for variables defined in var_variables. Each record represents "
            "a user's value for a variable within a Shifu or global/system scope. Important: "
            "This table stores user data (values), not variable definitions."
        )
    }

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    variable_value_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Variable value business identifier",
    )
    variable_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Variable business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Shifu business identifier (empty=global/system scope)",
    )
    user_bid = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="User business identifier",
    )
    key = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Variable key (fallback lookup)",
    )
    value = Column(
        Text,
        nullable=False,
        default="",
        comment="Variable value",
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
