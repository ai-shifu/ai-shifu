"""add demo shifu json file

Revision ID: a4d68cce5ce6
Revises: 21a3e778ef01
Create Date: 2025-11-12 14:41:07.381333

"""

import os
from io import BytesIO
from werkzeug.datastructures import FileStorage
from flaskr.service.user.models import User
from flaskr.common.dao import db
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.util import generate_id


# revision identifiers, used by Alembic.
revision = "a4d68cce5ce6"
down_revision = "21a3e778ef01"
branch_labels = None
depends_on = None


def upgrade():
    from flaskr.service.shifu.shifu_import_export_funcs import import_shifu
    from flask import current_app as app
    from flaskr.service.config.funcs import add_config

    with app.app_context():
        demo_shifu_file = (
            os.path.abspath(os.path.dirname(__file__)) + "/demo_shifu.json"
        )
        # Read file content first, then create FileStorage
        with open(demo_shifu_file, "rb") as f:
            file_content = f.read()

        # Create FileStorage from bytes
        file_storage = FileStorage(
            stream=BytesIO(file_content),
            filename=os.path.basename(demo_shifu_file),
            name="file",
        )

        shifu_bid = import_shifu(app, None, file_storage, "system")

        users = User.query.filter(User.is_creator == 1).all()
        for user in users:
            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user.user_id,
                AiCourseAuth.course_id == shifu_bid,
            ).first()
            if not auth:
                auth = AiCourseAuth(
                    course_auth_id=generate_id(app),
                    user_id=user.user_id,
                    course_id=shifu_bid,
                    auth_type="['view', 'edit', 'publish']",
                    status=1,
                )
                db.session.add(auth)
        db.session.commit()
        add_config(
            app,
            "DEMO_SHIFU_BID",
            shifu_bid,
            is_secret=False,
            remark="Demo shifu business identifier",
        )


def downgrade():
    pass
