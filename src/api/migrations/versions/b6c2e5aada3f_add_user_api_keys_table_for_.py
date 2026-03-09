"""add user_api_keys table for programmatic access

Revision ID: b6c2e5aada3f
Revises: 8f4c1a2b7d9e
Create Date: 2026-02-27 08:40:38.174983

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b6c2e5aada3f'
down_revision = '8f4c1a2b7d9e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_api_keys',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('api_key_bid', sa.String(length=32), nullable=False, comment='API key business identifier'),
    sa.Column('user_bid', sa.String(length=32), nullable=False, comment='Owner user business identifier'),
    sa.Column('key_hash', sa.String(length=128), nullable=False, comment='SHA-256 hash of the API key'),
    sa.Column('key_prefix', sa.String(length=12), nullable=False, comment='First 8 chars of key for display identification'),
    sa.Column('name', sa.String(length=100), nullable=False, comment='Human-readable key name'),
    sa.Column('last_used_at', sa.DateTime(), nullable=True, comment='Last usage timestamp'),
    sa.Column('revoked', sa.SmallInteger(), nullable=False, comment='Revoked flag: 0=active, 1=revoked'),
    sa.Column('deleted', sa.SmallInteger(), nullable=False, comment='Deletion flag: 0=active, 1=deleted'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='Creation timestamp'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
    sa.PrimaryKeyConstraint('id'),
    comment='User API keys for programmatic access'
    )
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_api_keys_api_key_bid'), ['api_key_bid'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_api_keys_deleted'), ['deleted'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_api_keys_key_hash'), ['key_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_api_keys_user_bid'), ['user_bid'], unique=False)


def downgrade():
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_api_keys_user_bid'))
        batch_op.drop_index(batch_op.f('ix_user_api_keys_key_hash'))
        batch_op.drop_index(batch_op.f('ix_user_api_keys_deleted'))
        batch_op.drop_index(batch_op.f('ix_user_api_keys_api_key_bid'))

    op.drop_table('user_api_keys')
