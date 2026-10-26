"""Keep ordinary login gates separate from verified contact and paid access."""

from types import SimpleNamespace

import pytest
from flaskr.service.common.dtos import UserInfo, has_login_identity

from tests.common.fixtures.local_identity import local_user_aggregate


@pytest.mark.parametrize("verified", [True, False])
def test_local_identity_fact_is_shared_by_aggregate_and_public_dto(
    verified: bool,
) -> None:
    aggregate = local_user_aggregate(verified=verified)
    public = aggregate.to_user_info()
    assert aggregate.has_local_password is verified
    assert public.has_local_password is verified
    assert has_login_identity(aggregate) is verified
    assert has_login_identity(public) is verified
    assert public.mobile == public.email == ""


def test_names_and_administrator_roles_without_credentials_do_not_log_in() -> None:
    aggregate = local_user_aggregate()
    aggregate.credentials.clear()
    assert aggregate.username
    assert aggregate.is_creator
    assert aggregate.is_operator
    assert not aggregate.has_local_password
    assert not has_login_identity(aggregate)
    assert not has_login_identity(aggregate.to_user_info())


@pytest.mark.parametrize("marker", [None, False, 0, 1, "true", "false", {}, []])
def test_non_boolean_markers_do_not_authenticate_guests(marker: object) -> None:
    guest = SimpleNamespace(
        username="local_owner",
        is_creator=True,
        is_operator=True,
        mobile="",
        email="",
        has_local_password=marker,
    )
    assert not has_login_identity(guest)
    public = UserInfo(
        user_id="guest",
        username="local_owner",
        name="Guest",
        mobile="",
        email="",
        user_state=0,
        wx_openid="",
        language="en-US",
        has_local_password=marker,
    )
    assert public.has_local_password is False
    assert not has_login_identity(public)


@pytest.mark.parametrize(
    ("mobile", "email"), [("13800000000", ""), ("", "learner@example.com")]
)
def test_legacy_contact_login_semantics_remain_compatible(
    mobile: str, email: str
) -> None:
    assert has_login_identity(SimpleNamespace(mobile=mobile, email=email))


def test_missing_user_has_no_login_identity() -> None:
    assert not has_login_identity(None)
