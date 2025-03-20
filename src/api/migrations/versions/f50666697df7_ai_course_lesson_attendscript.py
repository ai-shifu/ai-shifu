"""ai_course_lesson_attendscript

Revision ID: f50666697df7
Revises: 766207a9c1b1
Create Date: 2025-03-20 07:08:53.036447

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f50666697df7'
down_revision = '766207a9c1b1'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ai_course_lesson_attendscript', schema=None) as batch_op:
        batch_op.add_column(sa.Column('interaction_type', sa.Integer(), nullable=False, comment='Interaction type: 0-no interaction, 1-like, 2-dislike'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ai_course_lesson_attendscript', schema=None) as batch_op:
        batch_op.drop_column('interaction_type')

    # ### end Alembic commands ###
