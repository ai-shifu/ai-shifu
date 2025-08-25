"""add sys_user_language profile variable and copy from user_info

Revision ID: ac6b95629e7c
Revises: 0cbd676b770e
Create Date: 2025-08-18 13:05:01.074494

"""

from alembic import op
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = "ac6b95629e7c"
down_revision = "0cbd676b770e"
branch_labels = None
depends_on = None


def upgrade():
    # Data migration: copy user_language from user_info to user_profile as sys_user_language
    connection = op.get_bind()
    connection.execute(
        text(
            """
            INSERT INTO user_profile (user_id, profile_key, profile_value, profile_type, profile_id)
            SELECT u.user_id, 'sys_user_language', u.user_language, 2901, ''
            FROM user_info u
            LEFT JOIN user_profile up
                ON up.user_id = u.user_id
             AND up.profile_key = 'sys_user_language'
             AND up.profile_id = ''
            WHERE COALESCE(u.user_language, '') <> ''
                AND up.id IS NULL;
            """
        )
    )


def downgrade():
    # No-op: avoid deleting sys_user_language data to prevent data loss on rollback
    # The sys_user_language entries in user_profile will remain intact
    pass
