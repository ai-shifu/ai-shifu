"""Build server-resolved local identities without implying contact ownership."""

from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_REGISTERED,
)
from flaskr.service.user.repository import CredentialSummary, UserAggregate
from flaskr.util.datetime import now_utc


def local_user_aggregate(
    *, user_bid: str = "local-learner", verified: bool = True
) -> UserAggregate:
    """Return a real contactless aggregate with one explicit local credential."""
    timestamp = now_utc()
    return UserAggregate(
        user_bid=user_bid,
        identify=f"local:{user_bid}",
        nickname="Local owner",
        learner_profile="",
        learner_profile_updated_at=None,
        avatar="",
        birthday=None,
        language="en-US",
        state=USER_STATE_REGISTERED,
        deleted=False,
        created_at=timestamp,
        creator_activated_at=None,
        updated_at=timestamp,
        is_creator=True,
        is_operator=True,
        credentials=[
            CredentialSummary(
                credential_bid="local-credential",
                provider="password",
                metadata={"installation_admin": "true"},
                password_is_set=True,
                identifier="local_owner",
                subject_id="local_owner",
                subject_format="username",
                state=(
                    CREDENTIAL_STATE_VERIFIED
                    if verified
                    else CREDENTIAL_STATE_UNVERIFIED
                ),
            )
        ],
    )
