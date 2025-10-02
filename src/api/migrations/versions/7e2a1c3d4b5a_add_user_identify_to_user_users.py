"""add user_identify to user_users and backfill

Revision ID: 7e2a1c3d4b5a
Revises: 335301139812
Create Date: 2025-10-02 00:00:00

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7e2a1c3d4b5a"
down_revision = "335301139812"
branch_labels = None
depends_on = None


def upgrade():
    # Add column and index
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "user_identify",
                sa.String(length=255),
                nullable=False,
                server_default="",
                comment="User identifier: phone or email",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_user_users_user_identify"), ["user_identify"], unique=False
        )

    # Drop server default to match application-level default semantics
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.alter_column("user_identify", server_default=None)

    # Backfill data from legacy user_info
    bind = op.get_bind()
    engine = bind.engine
    metadata = sa.MetaData()

    user_users = sa.Table("user_users", metadata, autoload_with=engine)
    user_info = sa.Table("user_info", metadata, autoload_with=engine)

    CHUNK_SIZE = 1000
    last_pk = 0
    while True:
        with engine.connect() as read_conn:
            rows = (
                read_conn.execute(
                    sa.select(
                        user_users.c.id,
                        user_users.c.user_bid,
                        user_info.c.email,
                        user_info.c.mobile,
                    )
                    .select_from(
                        user_users.outerjoin(
                            user_info, user_info.c.user_id == user_users.c.user_bid
                        )
                    )
                    .where(user_users.c.id > last_pk)
                    .order_by(user_users.c.id.asc())
                    .limit(CHUNK_SIZE)
                )
                .mappings()
                .all()
            )

        if not rows:
            break

        with engine.begin() as write_conn:
            for row in rows:
                email = (row.get("email") or "").strip()
                mobile = (row.get("mobile") or "").strip()
                identify = email.lower() if email else mobile
                write_conn.execute(
                    user_users.update()
                    .where(user_users.c.id == row["id"])
                    .values(user_identify=identify)
                )
            last_pk = rows[-1]["id"]


def downgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_users_user_identify"))
        batch_op.drop_column("user_identify")
