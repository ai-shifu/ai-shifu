"""Pin the serialized account-profile keys the web client reads.

The learner web client decides whether to offer WeChat JSAPI payment from
``userInfo.openid``. That key is produced here and nowhere else, and a rename
would silently switch JSAPI off for every account rather than fail loudly --
frontend tests stub the field and cannot catch it. These assertions are the
contract.
"""

from __future__ import annotations

from flaskr.service.common.dtos import UserInfo
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.repository import (
    CredentialSummary,
    UserAggregate,
    build_user_info_from_aggregate,
)


def _user_info(wx_openid: str = "o_test_openid") -> UserInfo:
    return UserInfo(
        user_id="user-serialization-1",
        username="13800000000",
        name="Learner",
        email="",
        mobile="13800000000",
        user_state=1,
        wx_openid=wx_openid,
        language="zh-CN",
    )


def test_open_id_is_serialized_as_openid() -> None:
    payload = _user_info().__json__()

    assert payload["openid"] == "o_test_openid"


def test_unbound_account_serializes_an_empty_openid() -> None:
    payload = _user_info(wx_openid="").__json__()

    assert payload["openid"] == ""


def test_aggregate_open_id_reaches_the_serialized_payload() -> None:
    """The whole path: credential row -> aggregate -> DTO -> response key."""
    aggregate = UserAggregate(
        user_bid="user-serialization-2",
        identify="13800000000",
        nickname="Learner",
        learner_profile="",
        learner_profile_updated_at=None,
        avatar="",
        birthday=None,
        language="zh-CN",
        state=USER_STATE_REGISTERED,
        deleted=False,
        created_at=None,
        creator_activated_at=None,
        updated_at=None,
        credentials=[
            CredentialSummary(
                credential_bid="credential-serialization-2",
                provider="wechat",
                identifier="o_from_aggregate",
                subject_id="o_from_aggregate",
                subject_format="open_id",
                state=CREDENTIAL_STATE_VERIFIED,
            )
        ],
    )

    payload = build_user_info_from_aggregate(aggregate).__json__()

    assert payload["openid"] == "o_from_aggregate"
