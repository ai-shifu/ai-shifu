"""add dedao discount

Revision ID: 49f911fd70c5
Revises: 90fcbf121671
Create Date: 2024-09-18 08:17:04.040169

"""

# revision identifiers, used by Alembic.
revision = "49f911fd70c5"
down_revision = "90fcbf121671"
branch_labels = None
depends_on = None


def upgrade():
    from flaskr.service.order.discount import (
        generate_discount_code,
    )
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.consts import DISCOUNT_TYPE_FIXED, DISCOUNT_APPLY_TYPE_ALL
    from flaskr.dao import db
    from app import app

    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        # 减100元
        generate_discount_code(
            app,
            20,
            course_id,
            "2024-09-01",
            "2024-12-31",
            "DEDAO",
            discount_type=DISCOUNT_TYPE_FIXED,
            discount_apply_type=DISCOUNT_APPLY_TYPE_ALL,
            discount_count=1000,
            discount_code="DEDAO",
        )
        db.session.commit()


def downgrade():
    pass
