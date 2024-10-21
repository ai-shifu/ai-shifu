"""add ten discord

Revision ID: becca0e0502d
Revises: 1219f7486dc3
Create Date: 2024-09-04 09:12:27.101602

"""

# revision identifiers, used by Alembic.
revision = "becca0e0502d"
down_revision = "1219f7486dc3"
branch_labels = None
depends_on = None


def upgrade():
    from flaskr.service.order.discount import (
        generate_discount_code,
        generate_discount_code_by_rule,
    )
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.consts import (
        DISCOUNT_TYPE_FIXED,
        DISCOUNT_APPLY_TYPE_SPECIFIC,
    )
    from flaskr.dao import db
    from app import app

    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        # 减100元
        discount_id = generate_discount_code(
            app,
            10,
            course_id,
            "2024-09-01",
            "2024-12-31",
            "老带新",
            discount_type=DISCOUNT_TYPE_FIXED,
            discount_apply_type=DISCOUNT_APPLY_TYPE_SPECIFIC,
        )
        db.session.commit()
        for i in range(100):
            generate_discount_code_by_rule(app, discount_id)


def downgrade():
    pass
