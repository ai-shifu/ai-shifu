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
    for i, course_id in enumerate(old_shifu_bids):
        old_shifu_bid = course_id[0]
        old_course = AICourse.query.filter(AICourse.course_id == old_shifu_bid).first()
        print(
            f"migrate shifu draft to shifu draft v2, shifu_bid: {old_shifu_bid}, {old_course.course_name}, {i + 1}/{len(old_shifu_bids)}"
        )
        migrate_shifu_draft_to_shifu_draft_v2(current_app, old_shifu_bid)


def downgrade():
    pass
