"""Contact identifier resolution shared by admin flows.

The China site identifies people by SMS phone number and the overseas site by
Google/email; there is no region flag, so LOGIN_METHODS_ENABLED decides.
"""

from __future__ import annotations

import pytest
from flaskr.service.common import contact_identifiers
from flaskr.service.common.models import AppError


@pytest.fixture
def login_methods(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    def _set(value: str) -> None:
        monkeypatch.setattr(
            contact_identifiers,
            "get_config",
            lambda key, default=None: (
                value if key == "LOGIN_METHODS_ENABLED" else default
            ),
        )

    return _set


class TestResolveEnabledContactTypes:
    """Verify resolve enabled contact types behavior."""

    def test_google_login_implies_email(self, login_methods: set[str]) -> None:
        login_methods("google")
        assert contact_identifiers.resolve_enabled_contact_types() == {"email"}

    def test_phone_only_deployment(self, login_methods: set[str]) -> None:
        login_methods("phone,password")
        assert contact_identifiers.resolve_enabled_contact_types() == {"phone"}

    def test_mixed_deployment_keeps_both(self, login_methods: set[str]) -> None:
        login_methods("phone,email")
        assert contact_identifiers.resolve_enabled_contact_types() == {
            "phone",
            "email",
        }

    def test_unrecognized_methods_fall_back_to_phone(
        self, login_methods: set[str]
    ) -> None:
        login_methods("wechat")
        assert contact_identifiers.resolve_enabled_contact_types() == {"phone"}


class TestResolveContactType:
    """Verify resolve contact type behavior."""

    def test_single_enabled_type_wins_over_the_value(
        self, login_methods: set[str]
    ) -> None:
        # A malformed value must still fail with the error operators expect,
        # so the deployment's only contact type decides before the "@" check.
        login_methods("phone")
        assert contact_identifiers.resolve_contact_type("a@b.com") == "phone"
        login_methods("google")
        assert contact_identifiers.resolve_contact_type("13800138000") == "email"

    def test_mixed_deployment_infers_from_the_value(
        self, login_methods: set[str]
    ) -> None:
        login_methods("phone,email")
        assert contact_identifiers.resolve_contact_type("a@b.com") == "email"
        assert contact_identifiers.resolve_contact_type("13800138000") == "phone"


class TestValidateContactIdentifier:
    """Verify validate contact identifier behavior."""

    def test_email_is_lowercased_and_trimmed(self) -> None:
        assert (
            contact_identifiers.validate_contact_identifier(
                "  Teacher@Example.COM ", "email"
            )
            == "teacher@example.com"
        )

    def test_phone_drops_the_country_prefix(self) -> None:
        assert (
            contact_identifiers.validate_contact_identifier("+8613800138000", "phone")
            == "13800138000"
        )

    def test_phone_still_requires_an_sms_reachable_number(self) -> None:
        with pytest.raises(AppError):
            contact_identifiers.validate_contact_identifier("23800138000", "phone")

    def test_malformed_email_is_rejected(self) -> None:
        with pytest.raises(AppError):
            contact_identifiers.validate_contact_identifier("not-an-email", "email")

    def test_blank_value_uses_the_caller_error_key(self) -> None:
        with pytest.raises(AppError):
            contact_identifiers.validate_contact_identifier(
                "  ", "email", empty_error="creator_mobile"
            )

    def test_overlong_identifier_is_rejected(self) -> None:
        overlong = "a" * 320 + "@example.com"
        with pytest.raises(AppError):
            contact_identifiers.validate_contact_identifier(overlong, "email")


class TestResolveContactLookupProviders:
    """Verify resolve contact lookup providers behavior."""

    def test_email_also_matches_google_accounts(self) -> None:
        assert contact_identifiers.resolve_contact_lookup_providers("email") == [
            "email",
            "google",
        ]

    def test_phone_only_matches_phone(self) -> None:
        assert contact_identifiers.resolve_contact_lookup_providers("phone") == [
            "phone"
        ]
