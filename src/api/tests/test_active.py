from datetime import datetime, timedelta
from decimal import Decimal
import pytz


def test_save_active_creates_record(app):
    from flaskr.dao import db
    from flaskr.service.active.funcs import save_active
    from flaskr.service.active.models import Active

    with app.app_context():
        active_id = save_active(
            app,
            user_id="user-1",
            active_course="course-1",
            active_name="Early Bird",
            active_desc="Early bird discount",
            active_start_time="2025-01-01 00:00:00",
            active_end_time="2025-12-31 23:59:59",
            active_price=Decimal("9.99"),
            active_status=1,
        )

        saved = Active.query.filter(Active.active_id == active_id).first()
        assert saved is not None
        assert saved.active_course == "course-1"
        db.session.delete(saved)
        db.session.commit()


def test_query_and_join_active_creates_user_record(app):
    from flaskr.dao import db
    from flaskr.service.active.consts import (
        ACTIVE_JOIN_STATUS_ENABLE,
        ACTIVE_JOIN_TYPE_AUTO,
    )
    from flaskr.service.active.funcs import query_and_join_active
    from flaskr.service.active.models import Active

    now = datetime.now(pytz.timezone("Asia/Shanghai"))

    with app.app_context():
        active = Active(
            active_id="active-1",
            active_name="Auto Join",
            active_desc="Auto join active",
            active_status=1,
            active_start_time=now - timedelta(days=1),
            active_end_time=now + timedelta(days=1),
            active_price=Decimal("5.00"),
            active_course="course-1",
            active_join_type=ACTIVE_JOIN_TYPE_AUTO,
        )
        db.session.add(active)
        db.session.commit()

        records = query_and_join_active(app, "course-1", "user-1", "order-1")

        assert len(records) == 1
        assert records[0].status == ACTIVE_JOIN_STATUS_ENABLE
