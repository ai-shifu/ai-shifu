from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from flaskr.dao import db
from flaskr.service.profile.learner_profile import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
    get_learner_profile,
)
from flaskr.service.common.models import AppException
from flaskr.service.order.admin import (
    import_activation_order,
    normalize_mobile,
    parse_import_activation_entries,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import (
    create_user_entity,
    load_user_aggregate_by_identifier,
    upsert_credential,
)


PROFILE_UPDATED_AT = datetime(2026, 8, 12, 8, 30, tzinfo=timezone.utc)


def _stub_activation_order_side_effects(monkeypatch) -> None:
    import flaskr.service.order.admin as order_admin

    order = SimpleNamespace(
        order_bid="import-order",
        payable_price=None,
        paid_price=None,
        payment_channel="",
    )
    filtered_query = MagicMock()
    filtered_query.order_by.return_value.first.return_value = None
    filtered_query.first.return_value = order
    order_model = MagicMock()
    order_model.query.filter.return_value = filtered_query

    monkeypatch.setattr(order_admin, "Order", order_model)
    monkeypatch.setattr(
        order_admin,
        "init_buy_record",
        lambda *_args, **_kwargs: SimpleNamespace(order_id=order.order_bid),
    )
    monkeypatch.setattr(
        order_admin,
        "success_buy_record",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        order_admin,
        "ensure_demo_course_permissions",
        lambda *_args, **_kwargs: None,
    )


@pytest.mark.parametrize(
    ("input_phone", "expected"),
    [
        ("+8613800138004", "13800138004"),
        ("13800138004", "13800138004"),
        ("  +8613800138004  ", "13800138004"),
    ],
)
def test_normalize_mobile_handles_valid_edge_cases(input_phone, expected):
    assert normalize_mobile(input_phone) == expected


@pytest.mark.parametrize("input_phone", ["", None])
def test_normalize_mobile_rejects_empty_values(input_phone):
    with pytest.raises(AppException):
        normalize_mobile(input_phone)


def test_parse_import_activation_entries_phone_multiple_numbers():
    text = "12345678901 小明,13245678907,12345675432+美@美;"
    entries = parse_import_activation_entries(text, contact_type="phone")

    assert entries == [
        {"mobile": "12345678901", "nickname": "小明"},
        {"mobile": "13245678907", "nickname": ""},
        {"mobile": "12345675432", "nickname": "美@美"},
    ]


def test_parse_import_activation_entries_rejects_longer_digit_runs():
    text = "123456789012"
    entries = parse_import_activation_entries(text, contact_type="phone")

    assert entries == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Test@Example.com Alice",
            [{"mobile": "Test@Example.com", "nickname": "Alice"}],
        ),
        (
            "test@example.com张三",
            [{"mobile": "test@example.com", "nickname": "张三"}],
        ),
    ],
)
def test_parse_import_activation_entries_email_with_nickname(text, expected):
    entries = parse_import_activation_entries(text, contact_type="email")

    assert entries == expected


@pytest.mark.parametrize(
    ("contact_type", "identifier", "profile", "canonical_nickname", "has_state"),
    [
        (
            "phone",
            "13800138004",
            "可以叫我画像昵称。希望多用实际案例。",
            "画像昵称",
            False,
        ),
        ("email", "existing-profile@example.com", "", "", True),
    ],
    ids=["phone-profile", "email-cleared-state"],
)
def test_import_activation_keeps_pre_profile_nickname_behavior(
    app,
    monkeypatch,
    contact_type,
    identifier,
    profile,
    canonical_nickname,
    has_state,
):
    _stub_activation_order_side_effects(monkeypatch)

    with app.app_context():
        user = create_user_entity(
            user_bid=f"canonical-import-{contact_type}",
            identify=identifier,
            nickname=canonical_nickname,
            learner_profile=profile,
            learner_profile_updated_at=PROFILE_UPDATED_AT if profile else None,
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
        upsert_credential(
            app,
            user_bid=user.user_bid,
            provider_name=contact_type,
            subject_id=identifier,
            subject_format=contact_type,
            identifier=identifier,
            metadata={},
            verified=True,
        )
        if has_state:
            db.session.add(
                UserOnboardingState(
                    user_bid=user.user_bid,
                    scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                    version=PROFILE_ONBOARDING_VERSION,
                    status="completed",
                    trigger_source="settings",
                    completed_at=PROFILE_UPDATED_AT,
                )
            )
        db.session.commit()

        result = import_activation_order(
            app,
            identifier,
            "canonical-profile-course",
            "Imported nickname",
            contact_type=contact_type,
        )
        db.session.expire_all()
        stored_user = db.session.get(UserInfo, user.id)

        assert result == {"order_bid": "import-order"}
        assert stored_user is not None
        assert stored_user.nickname == "Imported nickname"


def test_import_activation_does_not_consult_profile_state_for_nickname_defaults(
    app,
    monkeypatch,
):
    import flaskr.service.order.admin as order_admin

    _stub_activation_order_side_effects(monkeypatch)

    with app.app_context():
        identifier = "13800138008"
        user = create_user_entity(
            user_bid="activation-import-lock-order",
            identify=identifier,
            nickname="Canonical Name",
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
        upsert_credential(
            app,
            user_bid=user.user_bid,
            provider_name="phone",
            subject_id=identifier,
            subject_format="phone",
            identifier=identifier,
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
                completed_at=PROFILE_UPDATED_AT,
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
                )
            )
            return original_first(query)

        original_ensure_user = order_admin.ensure_user_for_identifier

        def track_ensure_user(*args, **kwargs):
            reads_before_ensure.extend(read_order)
            return original_ensure_user(*args, **kwargs)

        monkeypatch.setattr(query_type, "first", track_first)
        monkeypatch.setattr(
            order_admin,
            "ensure_user_for_identifier",
            track_ensure_user,
        )

        result = import_activation_order(
            app,
            identifier,
            "canonical-profile-course",
            "Imported Name",
        )

        assert not any(
            read[0] == "user_onboarding_states" for read in reads_before_ensure
        )

        db.session.expire_all()
        stored_user = db.session.get(UserInfo, user.id)
        assert result == {"order_bid": "import-order"}
        assert stored_user is not None
        assert stored_user.nickname == "Imported Name"


@pytest.mark.parametrize(
    ("contact_type", "identifier"),
    [
        ("phone", "13800138005"),
        ("email", "new-profile@example.com"),
    ],
)
def test_import_activation_keeps_nickname_behavior_for_new_users(
    app,
    monkeypatch,
    contact_type,
    identifier,
):
    _stub_activation_order_side_effects(monkeypatch)

    with app.app_context():
        result = import_activation_order(
            app,
            identifier,
            "new-profile-course",
            "Imported nickname",
            contact_type=contact_type,
        )
        stored_user = load_user_aggregate_by_identifier(
            identifier,
            providers=[contact_type],
        )

        assert result == {"order_bid": "import-order"}
        assert stored_user is not None
        assert stored_user.nickname == "Imported nickname"
        assert (
            get_learner_profile(user_id=stored_user.user_bid)["legacy_profile_values"][
                "sys_user_nickname"
            ]
            == "Imported nickname"
        )


@pytest.mark.parametrize(
    ("contact_type", "identifier"),
    [
        ("phone", "13987654321"),
        ("email", "fallback-profile@example.com"),
    ],
)
def test_import_activation_identifier_fallback_is_not_profile_prefill(
    app,
    monkeypatch,
    contact_type,
    identifier,
):
    _stub_activation_order_side_effects(monkeypatch)

    with app.app_context():
        result = import_activation_order(
            app,
            identifier,
            "fallback-profile-course",
            contact_type=contact_type,
        )
        stored_user = load_user_aggregate_by_identifier(
            identifier,
            providers=[contact_type],
        )

        assert result == {"order_bid": "import-order"}
        assert stored_user is not None
        # Keep the compatibility field unchanged while excluding its
        # import-only fallback from the learner-owned profile draft.
        assert stored_user.nickname == identifier
        assert (
            get_learner_profile(user_id=stored_user.user_bid)["legacy_profile_values"]
            == {}
        )
