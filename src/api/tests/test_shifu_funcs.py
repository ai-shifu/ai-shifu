"""Verify course summaries and favorite scenarios."""

from flaskr.dao import db
from flaskr.service.shifu import funcs, shifu_publish_funcs
from flaskr.service.shifu.models import FavoriteScenario


def test_run_summary_with_error_handling_logs_and_continues(
    app: object, monkeypatch: object
) -> None:
    called = {"apply": False, "summary": False}

    def fake_apply(_snapshot: object) -> None:
        called["apply"] = True

    def fake_summary(_app: object, _shifu_id: object) -> None:
        called["summary"] = True
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(shifu_publish_funcs, "apply_shifu_context_snapshot", fake_apply)
    monkeypatch.setattr(shifu_publish_funcs, "get_shifu_summary", fake_summary)

    # Should not raise even if summary generation fails
    shifu_publish_funcs._run_summary_with_error_handling(app, "shifu-1")

    assert called["apply"] is True
    assert called["summary"] is True


def test_favorite_shifu_workflow(app: object) -> None:
    user_id = "test-user-123"
    shifu_id = "test-shifu-456"

    with app.app_context():
        # Cleanup first
        FavoriteScenario.query.filter_by(user_id=user_id, scenario_id=shifu_id).delete()
        db.session.commit()

        # Mark as favorite
        res = funcs.mark_favorite_shifu(app, user_id, shifu_id)
        assert res is True

        db.session.expire_all()
        fav = FavoriteScenario.query.filter_by(
            user_id=user_id, scenario_id=shifu_id
        ).first()
        assert fav is not None
        assert fav.status == 1

        # Unmark as favorite
        res = funcs.unmark_favorite_shifu(app, user_id, shifu_id)
        assert res is True

        db.session.expire_all()
        fav = FavoriteScenario.query.filter_by(
            user_id=user_id, scenario_id=shifu_id
        ).first()
        assert fav is not None
        assert fav.status == 0

        # Mark or unmark favorite helper
        res = funcs.mark_or_unmark_favorite_shifu(
            app, user_id, shifu_id, is_favorite=True
        )
        assert res is True
        db.session.expire_all()
        fav = FavoriteScenario.query.filter_by(
            user_id=user_id, scenario_id=shifu_id
        ).first()
        assert fav.status == 1

        res = funcs.mark_or_unmark_favorite_shifu(
            app, user_id, shifu_id, is_favorite=False
        )
        assert res is True
        db.session.expire_all()
        fav = FavoriteScenario.query.filter_by(
            user_id=user_id, scenario_id=shifu_id
        ).first()
        assert fav.status == 0
