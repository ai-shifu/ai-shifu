"""remove legacy timestamp server defaults

Revision ID: f6b2a4d8c9e0
Revises: e7f1a2b3c4d5
Create Date: 2026-07-04 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6b2a4d8c9e0"
down_revision = "e7f1a2b3c4d5"
branch_labels = None
depends_on = None


TIMESTAMP_COLUMNS = [
    ("var_variables", "created_at", "Creation timestamp"),
    ("var_variables", "updated_at", "Last update timestamp"),
    ("var_variable_values", "created_at", "Creation timestamp"),
    ("var_variable_values", "updated_at", "Last update timestamp"),
    ("promo_coupons", "created_at", "Creation timestamp"),
    ("promo_coupons", "updated_at", "Update timestamp"),
    ("promo_coupon_usages", "created_at", "Creation timestamp"),
    ("promo_coupon_usages", "updated_at", "Update timestamp"),
    ("promo_promos", "created_at", "Creation timestamp"),
    ("promo_promos", "updated_at", "Last update timestamp"),
    ("promo_redemptions", "created_at", "Creation timestamp"),
    ("promo_redemptions", "updated_at", "Last update timestamp"),
    ("learn_generated_elements", "created_at", "Creation timestamp"),
    ("learn_generated_elements", "updated_at", "Last update timestamp"),
    ("learn_lesson_feedbacks", "created_at", "Creation timestamp"),
    ("learn_lesson_feedbacks", "updated_at", "Last update timestamp"),
    ("bill_usage", "created_at", "Creation timestamp"),
    ("bill_usage", "updated_at", "Last update timestamp"),
]


def _set_server_default(server_default):
    table_columns = {}
    for table_name, column_name, comment in TIMESTAMP_COLUMNS:
        table_columns.setdefault(table_name, []).append((column_name, comment))

    for table_name, columns in table_columns.items():
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            for column_name, comment in columns:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.DateTime(),
                    existing_nullable=False,
                    existing_comment=comment,
                    server_default=server_default,
                )


def upgrade():
    _set_server_default(None)


def downgrade():
    _set_server_default(sa.text("CURRENT_TIMESTAMP"))
