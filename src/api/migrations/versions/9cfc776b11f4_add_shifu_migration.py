"""add_shifu_migration

Revision ID: 9cfc776b11f4
Revises: d9605bb33e67
Create Date: 2025-07-18 09:41:54.833515

"""

# revision identifiers, used by Alembic.
revision = "9cfc776b11f4"
down_revision = "d9605bb33e67"
branch_labels = None
depends_on = None


def upgrade():
    from flask import current_app
    from flaskr.service.shifu.migration import migrate_shifu_draft_to_shifu_draft_v2
    from flaskr.service.lesson.models import AICourse

    old_shifu_bids = AICourse.query.with_entities(AICourse.course_id).distinct().all()
    for old_shifu_bid in old_shifu_bids:
        migrate_shifu_draft_to_shifu_draft_v2(current_app, old_shifu_bid[0])


def downgrade():
    pass
