"""add inital course

Revision ID: a7806e012c77
Revises: df93b8df9291
Create Date: 2024-10-28 09:25:45.438604

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7806e012c77"
down_revision = "df93b8df9291"
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "course_keywords", sa.Text(), nullable=False, comment="Course keywords"
            )
        )
        batch_op.drop_column("course_teacher_avator")
        batch_op.add_column(
            sa.Column(
                "course_teacher_avator",
                sa.String(length=255),
                nullable=True,
                default="",
                server_default="",
                comment="Course teacher avatar",
            )
        )
        batch_op.drop_column("course_default_temprature")
        batch_op.add_column(
            sa.Column(
                "course_default_temprature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                default=0.3,
                server_default="0.3",
                comment="Course default temperature",
            )
        )
        batch_op.add_column(
            sa.Column(
                "course_default_temperature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                default=0.3,
                server_default="0.3",
                comment="Course default temperature",
            )
        )
        batch_op.add_column(
            sa.Column(
                "course_teacher_avatar",
                sa.String(length=255),
                nullable=False,
                default="",
                server_default="",
                comment="Course teacher avatar",
            )
        )
    with op.batch_alter_table("ai_lesson", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "parent_id",
                sa.String(length=36),
                nullable=False,
                comment="Parent lesson UUID",
            )
        )
        batch_op.drop_column("lesson_default_temprature")
        batch_op.add_column(
            sa.Column(
                "lesson_default_temprature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                default=0.3,
                server_default="0.3",
                comment="Lesson default temperature",
            )
        )
        batch_op.add_column(
            sa.Column(
                "lesson_default_temperature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                default=0.3,
                server_default="0.3",
                comment="Lesson default temperature",
            )
        )
    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "script_ui_profile_id",
                sa.String(length=36),
                nullable=False,
                comment="Script UI profile id",
            )
        )
        batch_op.drop_column("script_temprature")
        batch_op.add_column(
            sa.Column(
                "script_temprature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                default=0.3,
                server_default="0.3",
                comment="Script temperature",
            )
        )
        batch_op.add_column(
            sa.Column(
                "script_temperature",
                sa.DECIMAL(precision=3, scale=1),
                nullable=False,
                comment="Script temperature",
            )
        )

    from flaskr.service.lesson.funs import update_lesson_info
    from flaskr.service.lesson.const import (
        LESSON_TYPE_TRIAL,
        LESSON_TYPE_BRANCH_HIDDEN,
    )
    from flaskr.util.uuid import generate_id
    from flask import current_app
    import os

    doc_id = generate_id(current_app)
    view_id = generate_id(current_app)
    course_id = generate_id(current_app)
    course_name = os.path.abspath(os.path.dirname(__file__))
    update_lesson_info(
        current_app,
        doc_id,
        "tblMH4LUaSfDwRqr",
        view_id,
        "初次体验沟通",
        0,
        LESSON_TYPE_TRIAL,
        course_id=course_id,
        file_name=course_name + "/init_course/00.json",
    )
    update_lesson_info(
        current_app,
        doc_id,
        "tbl453exjXgUq7Sc",
        view_id,
        "进入下一步",
        1,
        LESSON_TYPE_TRIAL,
        course_id=course_id,
        file_name=course_name + "/init_course/01.json",
    )
    update_lesson_info(
        current_app,
        doc_id,
        "tblDEvaHJAIkIfst",
        view_id,
        "学习课程",
        21,
        LESSON_TYPE_BRANCH_HIDDEN,
        course_id=course_id,
        file_name=course_name + "/init_course/21.json",
    )
    update_lesson_info(
        current_app,
        doc_id,
        "tblcQxIckOB8r2s9",
        view_id,
        "课程合作",
        22,
        LESSON_TYPE_BRANCH_HIDDEN,
        course_id=course_id,
        file_name=course_name + "/init_course/22.json",
    )
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.drop_column("course_keywords")
        batch_op.execute(
            "UPDATE ai_course SET course_default_temprature = course_default_temperature"
        )
        batch_op.drop_column("course_default_temperature")
        batch_op.execute(
            "UPDATE ai_course SET course_teacher_avator = course_teacher_avatar"
        )
        batch_op.drop_column("course_teacher_avatar")

    with op.batch_alter_table("ai_lesson", schema=None) as batch_op:
        batch_op.drop_column(batch_op.f("parent_id"))
        batch_op.execute(
            "UPDATE ai_lesson SET lesson_default_temprature = lesson_default_temperature"
        )
        batch_op.drop_column("lesson_default_temperature")

    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.drop_column(batch_op.f("script_ui_profile_id"))
        batch_op.execute(
            "UPDATE ai_lesson_script SET script_temprature = script_temperature"
        )
        batch_op.drop_column("script_temperature")


def downgrade():
    pass
