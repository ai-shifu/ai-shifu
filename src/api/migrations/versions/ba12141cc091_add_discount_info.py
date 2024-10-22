"""add discount  info

Revision ID: ba12141cc091
Revises: 018739878ae2
Create Date: 2024-08-19 06:34:51.804852

"""

# revision identifiers, used by Alembic.
revision = "ba12141cc091"
down_revision = "018739878ae2"
branch_labels = None
depends_on = None


def upgrade():
    from flaskr.service.order.discount import (
        generate_discount_code,
        generate_discount_code_by_rule,
    )
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.models import Discount
    from flaskr.service.order.consts import (
        DISCOUNT_TYPE_FIXED,
        DISCOUNT_APPLY_TYPE_SPECIFIC,
    )
    from flaskr.dao import db
    from app import app

    print("upgrade")
    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        discount = Discount.query.first()
        if not discount:
            # 减100元

            discount_id = generate_discount_code(
                app,
                100,
                course_id,
                "2024-09-01",
                "2024-12-31",
                "channel",
                discount_type=DISCOUNT_TYPE_FIXED,
                discount_apply_type=DISCOUNT_APPLY_TYPE_SPECIFIC,
            )

            db.session.commit()
            for i in range(10):
                generate_discount_code_by_rule(app, discount_id)

            # 减100元
            discount_id = generate_discount_code(
                app,
                200,
                course_id,
                "2024-09-01",
                "2024-12-31",
                "channel",
                discount_type=DISCOUNT_TYPE_FIXED,
                discount_apply_type=DISCOUNT_APPLY_TYPE_SPECIFIC,
            )

            db.session.commit()
            for i in range(10):
                generate_discount_code_by_rule(app, discount_id)
    pass


def downgrade():
    pass
