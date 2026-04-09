"""backfill operator for first verified user

Revision ID: 2b7c9d1e4f6a
Revises: 1f2e3d4c5b6a
Create Date: 2026-04-04 13:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2b7c9d1e4f6a"
down_revision = "1f2e3d4c5b6a"
branch_labels = None
depends_on = None


# VERIFIED_STATES includes both legacy public state codes (1/2/3) and the
# canonical stored codes (1102/1103/1104) so upgraded historical rows are
# still recognized before all records are normalized.
VERIFIED_STATES = (1, 2, 3, 1102, 1103, 1104)


def upgrade():
    bind = op.get_bind()

    # Respect instances that already assigned operator manually after the
    # schema rollout. Only backfill when no active operator exists yet.
    existing_operator = bind.execute(
        sa.text(
            """
            SELECT id
            FROM user_users
            WHERE deleted = 0 AND is_operator = 1
            LIMIT 1
            """
        )
    ).scalar()
    if existing_operator is not None:
        return

    bind.execute(
        sa.text(
            """
            UPDATE user_users
            SET is_operator = 1
            WHERE id = (
                SELECT candidate.id
                FROM (
                    SELECT id
                    FROM user_users
                    WHERE deleted = 0
                      AND state IN :verified_states
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                ) AS candidate
            )
            """
        ).bindparams(sa.bindparam("verified_states", expanding=True)),
        {"verified_states": VERIFIED_STATES},
    )


def downgrade():
    # No-op: the upgrade is an additive one-time backfill and cannot safely
    # distinguish migrated values from later manual operator assignments.
    return
