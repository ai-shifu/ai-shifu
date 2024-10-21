"""add active info

Revision ID: 018739878ae2
Revises: 2c92dff25922
Create Date: 2024-08-19 06:34:15.845706

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "018739878ae2"
down_revision = "2c92dff25922"
branch_labels = None
depends_on = None


def upgrade():
    import datetime
    from flaskr.service.active.funcs import create_active
    from flaskr.service.active.models import Active
    from flaskr.service.lesson.models import AICourse
    from app import app

    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        active_name = "早鸟价格立减"
        active_desc = "早鸟活动"
        active_type = 1
        active = Active.query.filter(Active.active_name == active_name).first()
        if active:
            app.logger.info("活动已存在")
            return
        active_id = create_active(
            app, course_id, active_name, active_desc, "2024-01-1", "2024-9-1", 100
        )


def downgrade():
    pass
