"""Verify course summaries and favorite scenarios."""

from flaskr.dao import db
from flaskr.service.shifu import funcs
from flaskr.service.shifu.models import FavoriteScenario


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
