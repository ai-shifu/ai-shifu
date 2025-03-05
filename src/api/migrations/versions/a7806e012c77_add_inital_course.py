"""add inital course

Revision ID: a7806e012c77
Revises: df93b8df9291
Create Date: 2024-10-28 09:25:45.438604

"""

# revision identifiers, used by Alembic.
revision = "a7806e012c77"
down_revision = "df93b8df9291"
branch_labels = None
depends_on = None


def upgrade():

    try:
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
        course_name = os.path.abspath(
            os.path.dirname(__file__)
        )  # 获取当前文件的绝对路径
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
    except Exception:
        pass


def downgrade():
    pass
