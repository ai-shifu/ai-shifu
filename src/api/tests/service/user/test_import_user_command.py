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
def test_import_user_keeps_pre_profile_nickname_behavior(
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
        mobile = "13990001001" if canonical_source == "profile" else "13990001002"
        user = create_user_entity(
            user_bid=f"import-user-{canonical_source}",
            identify=mobile,
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
            subject_id=mobile,
            subject_format="phone",
            identifier=mobile,
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
            mobile,
            "course-for-import",
            user_nick_name="Imported Name",
        )
        db.session.expire_all()
        stored_user = db.session.get(UserInfo, user.id)

        assert stored_user is not None
        assert stored_user.nickname == "Imported Name"


def test_import_user_does_not_consult_profile_state_before_nickname_defaults(
    app,
    monkeypatch,
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
        mobile = "13990001003"
        user = create_user_entity(
            user_bid="import-user-lock-order",
            identify=mobile,
            nickname="Canonical Name",
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
        upsert_credential(
            app,
            user_bid=user.user_bid,
            provider_name="phone",
            subject_id=mobile,
            subject_format="phone",
            identifier=mobile,
            metadata={},
            verified=True,
        )
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

        query_type = type(UserInfo.query)
        original_first = query_type.first
        read_order: list[tuple[str, str, bool, bool]] = []
        reads_before_ensure: list[tuple[str, str, bool, bool]] = []

        def track_first(query):
            statement = str(query.statement)
            parameters = query.statement.compile().params
            lookup_value = str(
                parameters.get("user_bid_1") or parameters.get("user_identify_1", "")
            )
            table = (
                "user_onboarding_states"
                if "user_onboarding_states" in statement
                else "user_users"
                if "user_users" in statement
                else "other"
            )
            read_order.append(
                (
                    table,
                    lookup_value,
                    query._for_update_arg is not None,
                    bool(query.load_options._populate_existing),
                ),
            )
            return original_first(query)

        original_ensure_user = import_user_module.ensure_user_for_identifier

        def track_ensure_user(*args, **kwargs):
            reads_before_ensure.extend(read_order)
            return original_ensure_user(*args, **kwargs)

        monkeypatch.setattr(query_type, "first", track_first)
        monkeypatch.setattr(
            import_user_module,
            "ensure_user_for_identifier",
            track_ensure_user,
        )

        import_user(
            app,
            mobile,
            "course-for-import",
            user_nick_name="Imported Name",
        )

        assert not any(
            read[0] == "user_onboarding_states" for read in reads_before_ensure
        )

        db.session.expire_all()
        stored_user = db.session.get(UserInfo, user.id)
        assert stored_user is not None
        assert stored_user.nickname == "Imported Name"
