"""add demo shifu json file

Revision ID: a4d68cce5ce6
Revises: 21a3e778ef01
Create Date: 2025-11-12 14:41:07.381333

"""

# revision identifiers, used by Alembic.
revision = "a4d68cce5ce6"
down_revision = "21a3e778ef01"
branch_labels = None
depends_on = None


import os


def upgrade():
    from flask import current_app as app
    from flaskr.command.update_shifu_demo import update_demo_shifu

    with app.app_context():
        if os.getenv("SKIP_DEMO_SHIFU_IMPORT"):
            app.logger.info("Skip demo shifu import due to SKIP_DEMO_SHIFU_IMPORT")
            return
        update_demo_shifu(app)


def downgrade():
    pass
