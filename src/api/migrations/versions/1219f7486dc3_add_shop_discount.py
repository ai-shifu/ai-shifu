"""add shop discount

Revision ID: 1219f7486dc3
Revises: 9f7551112af0
Create Date: 2024-08-26 01:31:42.211917

"""

# revision identifiers, used by Alembic.
revision = "1219f7486dc3"
down_revision = "9f7551112af0"
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
            200,
            course_id,
            "2024-09-01",
            "2024-12-31",
            "首发直播",
            discount_type=DISCOUNT_TYPE_FIXED,
            discount_apply_type=DISCOUNT_APPLY_TYPE_SPECIFIC,
        )
        db.session.commit()
        for i in range(500):
            generate_discount_code_by_rule(app, discount_id)


def downgrade():
    pass
