"""migrate to MarkdownFlow

Revision ID: 63a0479d46e3
Revises: c10b5c691b59
Create Date: 2025-09-10 15:28:38.689844

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "63a0479d46e3"
down_revision = "c10b5c691b59"
branch_labels = None
depends_on = None


def upgrade():
    from flaskr.service.shifu.migration import migrate_shifu_to_mdflow_content
    from flaskr.service.shifu.models import DraftShifu
    from flask import current_app
    from sqlalchemy import text
    import time

    with current_app.app_context():
        old_shifu_bids = (
            DraftShifu.query.with_entities(DraftShifu.shifu_bid).distinct().all()
        )
        connection = op.get_bind()
        for i, shifu_bid in enumerate(old_shifu_bids):
            shifu_bid = shifu_bid[0]
            print(
                f"migrate shifu to markdown content, shifu_bid: {shifu_bid}, {i + 1}/{len(old_shifu_bids)}"
            )
            migrate_shifu_to_mdflow_content(current_app, shifu_bid)
            connection.execute(text("SELECT now()"))
            time.sleep(1)
    pass


def downgrade():
    pass
