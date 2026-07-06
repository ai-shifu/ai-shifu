from datetime import datetime, timezone

from flaskr.util.datetime import now_utc


def test_now_utc_returns_naive_utc() -> None:
    value = now_utc()
    # Naive (tz-unaware) so it stays comparable with existing naive timestamps.
    assert value.tzinfo is None
    # Value tracks real UTC, independent of the process TZ.
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((reference - value).total_seconds()) < 5


def test_model_timestamp_default_writes_utc(app) -> None:
    """ORM default (now_utc) must persist UTC, not DB-session local time."""
    from flaskr import dao
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        row = UserVerifyCode()
        dao.db.session.add(row)
        dao.db.session.commit()

        created = row.created
        assert created.tzinfo is None
        reference = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((reference - created).total_seconds()) < 60
