"""add notification record operator indexes

Revision ID: f4a6b8c2d9e1
Revises: e3b1c2d4f5a6
Create Date: 2026-05-25 18:30:00.000000

"""

from __future__ import annotations

from alembic import op


revision = "f4a6b8c2d9e1"
down_revision = "e3b1c2d4f5a6"
branch_labels = None
depends_on = None


_INDEXES = (
    (
        "ix_notification_records_deleted_created_id",
        ["deleted", "created_at", "id"],
    ),
    (
        "ix_notification_records_deleted_status_created_id",
        ["deleted", "status", "created_at", "id"],
    ),
    (
        "ix_notification_records_deleted_source_type_created_id",
        ["deleted", "source_type", "created_at", "id"],
    ),
    (
        "ix_notification_records_deleted_type_created_id",
        ["deleted", "notification_type", "created_at", "id"],
    ),
)


def upgrade():
    for index_name, columns in _INDEXES:
        op.create_index(index_name, "notification_records", columns, unique=False)


def downgrade():
    for index_name, _columns in reversed(_INDEXES):
        op.drop_index(index_name, table_name="notification_records")
