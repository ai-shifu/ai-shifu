"""reorder columns and update table comments for shifu models

Revision ID: reorder_shifu_columns
Revises: 31f18de7e03e
Create Date: 2025-08-13 20:15:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "reorder_shifu_columns"
down_revision = "31f18de7e03e"
branch_labels = None
depends_on = None


def upgrade():
    """
    Reorder columns and update table comments for shifu models according to database design standards.

    Column order standards:
    1. id (primary key)
    2. [table_name]_bid (business identifier)
    3. External business identifiers (foreign keys, child before parent)
    4. Business columns
    5. status (if applicable)
    6. deleted
    7. created_at
    8. created_user_bid (if applicable)
    9. updated_at
    10. updated_user_bid (if applicable)
    """

    # Update table comments
    op.execute(
        "ALTER TABLE scenario_favorite COMMENT 'User favorite scenario entities'"
    )
    op.execute(
        "ALTER TABLE scenario_resource COMMENT 'Scenario resource mapping entities'"
    )
    op.execute("ALTER TABLE ai_course_auth COMMENT 'AI course authorization entities'")
    op.execute("ALTER TABLE shifu_draft_shifus COMMENT 'Draft shifu entities'")
    op.execute(
        "ALTER TABLE shifu_draft_outline_items COMMENT 'Draft outline item entities'"
    )
    op.execute("ALTER TABLE shifu_draft_blocks COMMENT 'Draft block entities'")
    op.execute(
        "ALTER TABLE shifu_log_draft_structs COMMENT 'Draft structure log entities'"
    )
    op.execute("ALTER TABLE shifu_published_shifus COMMENT 'Published shifu entities'")
    op.execute(
        "ALTER TABLE shifu_published_outline_items COMMENT 'Published outline item entities'"
    )
    op.execute("ALTER TABLE shifu_published_blocks COMMENT 'Published block entities'")
    op.execute(
        "ALTER TABLE shifu_log_published_structs COMMENT 'Published structure log entities'"
    )

    # === REORDER scenario_favorite COLUMNS ===
    # Add missing columns first
    op.add_column(
        "scenario_favorite",
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Deletion flag: 0=active, 1=deleted",
        ),
    )
    op.add_column(
        "scenario_favorite",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
    )

    # Reorder columns: id, scenario_id, user_id, status, deleted, created_at, updated_at
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN scenario_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Scenario UUID' AFTER id"
    )
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN user_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'User UUID' AFTER scenario_id"
    )
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN status INT NOT NULL DEFAULT 0 COMMENT 'Status' AFTER user_id"
    )
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN deleted SMALLINT NOT NULL DEFAULT 0 COMMENT 'Deletion flag: 0=active, 1=deleted' AFTER status"
    )
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp' AFTER deleted"
    )
    op.execute(
        "ALTER TABLE scenario_favorite MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp' AFTER created_at"
    )

    # Add indexes
    op.create_index(
        "ix_scenario_favorite_scenario_id", "scenario_favorite", ["scenario_id"]
    )
    op.create_index("ix_scenario_favorite_user_id", "scenario_favorite", ["user_id"])
    op.create_index("ix_scenario_favorite_deleted", "scenario_favorite", ["deleted"])

    # === REORDER scenario_resource COLUMNS ===
    # Add missing updated_at column and rename is_deleted to deleted
    op.add_column(
        "scenario_resource",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
    )
    op.alter_column(
        "scenario_resource",
        "is_deleted",
        new_column_name="deleted",
        existing_type=sa.Integer(),
        type_=sa.SmallInteger(),
    )

    # Reorder columns: id, resource_resource_id, scenario_id, chapter_id, resource_id, resource_type, deleted, created_at, updated_at
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN resource_resource_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Resource UUID' AFTER id"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN scenario_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Scenario UUID' AFTER resource_resource_id"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN chapter_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Chapter UUID' AFTER scenario_id"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN resource_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Resource UUID' AFTER chapter_id"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN resource_type INT NOT NULL DEFAULT 0 COMMENT 'Resource type' AFTER resource_id"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN deleted SMALLINT NOT NULL DEFAULT 0 COMMENT 'Deletion flag: 0=active, 1=deleted' AFTER resource_type"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp' AFTER deleted"
    )
    op.execute(
        "ALTER TABLE scenario_resource MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp' AFTER created_at"
    )

    op.create_index("ix_scenario_resource_deleted", "scenario_resource", ["deleted"])

    # === REORDER ai_course_auth COLUMNS ===
    # Add missing deleted column
    op.add_column(
        "ai_course_auth",
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Deletion flag: 0=active, 1=deleted",
        ),
    )

    # Reorder columns: id, course_auth_id, course_id, user_id, auth_type, status, deleted, created_at, updated_at
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN course_auth_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Course auth UUID' AFTER id"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN course_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'Course UUID' AFTER course_auth_id"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN user_id VARCHAR(36) NOT NULL DEFAULT '' COMMENT 'User UUID' AFTER course_id"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN auth_type VARCHAR(255) NOT NULL DEFAULT '[]' COMMENT 'Authorization type: 1=read, 2=write, 3=delete, 4=publish' AFTER user_id"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN status INT NOT NULL DEFAULT 0 COMMENT 'Status' AFTER auth_type"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN deleted SMALLINT NOT NULL DEFAULT 0 COMMENT 'Deletion flag: 0=active, 1=deleted' AFTER status"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp' AFTER deleted"
    )
    op.execute(
        "ALTER TABLE ai_course_auth MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp' AFTER created_at"
    )

    # Add indexes
    op.create_index("ix_ai_course_auth_course_id", "ai_course_auth", ["course_id"])
    op.create_index("ix_ai_course_auth_user_id", "ai_course_auth", ["user_id"])
    op.create_index("ix_ai_course_auth_deleted", "ai_course_auth", ["deleted"])

    # === REORDER shifu_draft_blocks COLUMNS ===
    # Reorder foreign keys: outline_item_bid (child) before shifu_bid (parent)
    op.execute(
        "ALTER TABLE shifu_draft_blocks MODIFY COLUMN block_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Block business identifier' AFTER id"
    )
    op.execute(
        "ALTER TABLE shifu_draft_blocks MODIFY COLUMN outline_item_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Outline item business identifier' AFTER block_bid"
    )
    op.execute(
        "ALTER TABLE shifu_draft_blocks MODIFY COLUMN shifu_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Shifu business identifier' AFTER outline_item_bid"
    )

    # === REORDER shifu_published_blocks COLUMNS ===
    # Reorder foreign keys: outline_item_bid (child) before shifu_bid (parent)
    op.execute(
        "ALTER TABLE shifu_published_blocks MODIFY COLUMN block_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Block business identifier' AFTER id"
    )
    op.execute(
        "ALTER TABLE shifu_published_blocks MODIFY COLUMN outline_item_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Outline item business identifier' AFTER block_bid"
    )
    op.execute(
        "ALTER TABLE shifu_published_blocks MODIFY COLUMN shifu_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Shifu business identifier' AFTER outline_item_bid"
    )

    # Add indexes for deleted columns on existing shifu tables
    op.create_index("ix_shifu_draft_shifus_deleted", "shifu_draft_shifus", ["deleted"])
    op.create_index(
        "ix_shifu_draft_outline_items_deleted", "shifu_draft_outline_items", ["deleted"]
    )
    op.create_index("ix_shifu_draft_blocks_deleted", "shifu_draft_blocks", ["deleted"])
    op.create_index(
        "ix_shifu_log_draft_structs_deleted", "shifu_log_draft_structs", ["deleted"]
    )
    op.create_index(
        "ix_shifu_published_shifus_deleted", "shifu_published_shifus", ["deleted"]
    )
    op.create_index(
        "ix_shifu_published_outline_items_deleted",
        "shifu_published_outline_items",
        ["deleted"],
    )
    op.create_index(
        "ix_shifu_published_blocks_deleted", "shifu_published_blocks", ["deleted"]
    )
    op.create_index(
        "ix_shifu_log_published_structs_deleted",
        "shifu_log_published_structs",
        ["deleted"],
    )

    # Add indexes for user tracking columns
    op.create_index(
        "ix_shifu_draft_shifus_created_user_bid",
        "shifu_draft_shifus",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_draft_outline_items_created_user_bid",
        "shifu_draft_outline_items",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_draft_blocks_created_user_bid",
        "shifu_draft_blocks",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_log_draft_structs_created_user_bid",
        "shifu_log_draft_structs",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_published_shifus_created_user_bid",
        "shifu_published_shifus",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_published_outline_items_created_user_bid",
        "shifu_published_outline_items",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_published_blocks_created_user_bid",
        "shifu_published_blocks",
        ["created_user_bid"],
    )
    op.create_index(
        "ix_shifu_log_published_structs_created_user_bid",
        "shifu_log_published_structs",
        ["created_user_bid"],
    )

    # Update all shifu table timestamp columns to use server_default and ensure proper ordering
    shifu_tables = [
        "shifu_draft_shifus",
        "shifu_draft_outline_items",
        "shifu_draft_blocks",
        "shifu_log_draft_structs",
        "shifu_published_shifus",
        "shifu_published_outline_items",
        "shifu_published_blocks",
        "shifu_log_published_structs",
    ]

    for table in shifu_tables:
        # Update timestamp columns with proper server defaults
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp'"
        )
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp'"
        )

        # Ensure standard column ordering for shifu tables: deleted, created_at, created_user_bid, updated_at, updated_user_bid
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN deleted SMALLINT NOT NULL DEFAULT 0 COMMENT 'Deletion flag: 0=active, 1=deleted'"
        )
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation timestamp' AFTER deleted"
        )
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN created_user_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Creator user business identifier' AFTER created_at"
        )
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp' AFTER created_user_bid"
        )
        op.execute(
            f"ALTER TABLE {table} MODIFY COLUMN updated_user_bid VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Last updater user business identifier' AFTER updated_at"
        )


def downgrade():
    """
    Reverse the changes made in upgrade().
    """

    # Remove table comments (MySQL doesn't have a direct way to remove comments, so set to empty)
    op.execute("ALTER TABLE scenario_favorite COMMENT ''")
    op.execute("ALTER TABLE scenario_resource COMMENT ''")
    op.execute("ALTER TABLE ai_course_auth COMMENT ''")
    op.execute("ALTER TABLE shifu_draft_shifus COMMENT ''")
    op.execute("ALTER TABLE shifu_draft_outline_items COMMENT ''")
    op.execute("ALTER TABLE shifu_draft_blocks COMMENT ''")
    op.execute("ALTER TABLE shifu_log_draft_structs COMMENT ''")
    op.execute("ALTER TABLE shifu_published_shifus COMMENT ''")
    op.execute("ALTER TABLE shifu_published_outline_items COMMENT ''")
    op.execute("ALTER TABLE shifu_published_blocks COMMENT ''")
    op.execute("ALTER TABLE shifu_log_published_structs COMMENT ''")

    # Remove added indexes
    op.drop_index("ix_scenario_favorite_scenario_id", "scenario_favorite")
    op.drop_index("ix_scenario_favorite_user_id", "scenario_favorite")
    op.drop_index("ix_scenario_favorite_deleted", "scenario_favorite")
    op.drop_index("ix_ai_course_auth_course_id", "ai_course_auth")
    op.drop_index("ix_ai_course_auth_user_id", "ai_course_auth")
    op.drop_index("ix_ai_course_auth_deleted", "ai_course_auth")
    op.drop_index("ix_scenario_resource_deleted", "scenario_resource")

    # Remove shifu table indexes
    shifu_tables = [
        "shifu_draft_shifus",
        "shifu_draft_outline_items",
        "shifu_draft_blocks",
        "shifu_log_draft_structs",
        "shifu_published_shifus",
        "shifu_published_outline_items",
        "shifu_published_blocks",
        "shifu_log_published_structs",
    ]

    for table in shifu_tables:
        op.drop_index(f"ix_{table}_deleted", table)
        op.drop_index(f"ix_{table}_created_user_bid", table)

    # Remove added columns
    op.drop_column("scenario_favorite", "deleted")
    op.drop_column("scenario_favorite", "updated_at")
    op.drop_column("scenario_resource", "updated_at")
    op.drop_column("ai_course_auth", "deleted")

    # Revert column changes
    op.alter_column(
        "scenario_favorite",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.TIMESTAMP(),
        nullable=False,
        comment="Creation time",
    )
    op.alter_column(
        "scenario_resource",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.TIMESTAMP(),
        nullable=False,
        comment="Creation time",
    )
    op.alter_column(
        "scenario_resource",
        "deleted",
        new_column_name="is_deleted",
        existing_type=sa.SmallInteger(),
        type_=sa.Integer(),
        nullable=False,
        comment="Is deleted",
    )
    op.alter_column(
        "ai_course_auth",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.TIMESTAMP(),
        nullable=False,
        comment="Creation time",
    )
    op.alter_column(
        "ai_course_auth",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=sa.TIMESTAMP(),
        nullable=False,
        comment="Update time",
    )

    # Revert shifu table timestamp columns
    for table in shifu_tables:
        op.alter_column(
            table,
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=None,
            comment="Creation timestamp",
        )
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=None,
            comment="Last update timestamp",
        )
