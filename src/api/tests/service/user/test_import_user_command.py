from importlib import import_module
from types import SimpleNamespace

import pytest

from flaskr.command.import_user import import_user
from flaskr.dao import db
from flaskr.service.profile.learner_profile import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity, upsert_credential
from flaskr.util.datetime import now_utc


@pytest.mark.parametrize("canonical_source", ["profile", "cleared-state"])
def test_import_user_preserves_canonical_profile_nickname(
    app,
    monkeypatch,
    canonical_source,
):
    import_user_module = import_module("flaskr.command.import_user")

    monkeypatch.setattr(
        import_user_module,
        "init_buy_record",
        lambda *_args, **_kwargs: SimpleNamespace(order_id="manual-order"),
    )
    monkeypatch.setattr(
        import_user_module,
        "use_coupon_code",
        lambda *_args, **_kwargs: None,
    )

    with app.app_context():
        user = create_user_entity(
            user_bid=f"import-user-{canonical_source}",
            identify="13800138006",
            nickname="Canonical Name",
            learner_profile=(
                "Please call me Canonical Name."
                if canonical_source == "profile"
                else ""
            ),
            learner_profile_updated_at=(
                now_utc() if canonical_source == "profile" else None
            ),
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
        upsert_credential(
            app,
            user_bid=user.user_bid,
            provider_name="phone",
            subject_id="13800138006",
            subject_format="phone",
            identifier="13800138006",
            metadata={},
            verified=True,
        )
        if canonical_source == "cleared-state":
            db.session.add(
                UserOnboardingState(
                    user_bid=user.user_bid,
                    scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                    version=PROFILE_ONBOARDING_VERSION,
                    status="completed",
                    trigger_source="settings",
                    completed_at=now_utc(),
                )
            )
        db.session.commit()

        import_user(
            app,
            "13800138006",
            "course-for-import",
            user_nick_name="Imported Name",
        )
        db.session.expire_all()
        stored_user = db.session.get(UserInfo, user.id)

        assert stored_user is not None
        assert stored_user.nickname == "Canonical Name"
