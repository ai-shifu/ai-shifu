"""Unit tests for creator-analytics PII redaction and masking helpers."""

from __future__ import annotations

from flaskr.service.creator_analytics.pii import (
    mask_user_identify,
    redact_pii,
)


# ---------------------------------------------------------------------------
# redact_pii — existing behaviour must not regress
# ---------------------------------------------------------------------------


def test_redact_phone_in_nickname() -> None:
    assert redact_pii("张三 13812345678") == "张三 [REDACTED-PHONE]"


def test_redact_email_in_nickname() -> None:
    assert (
        redact_pii("contact me at foo@bar.com ok")
        == "contact me at [REDACTED-EMAIL] ok"
    )


def test_redact_id_card() -> None:
    text = "id: 11010119900307151X"
    assert "[REDACTED-IDCARD]" in redact_pii(text)


def test_redact_empty_string_unchanged() -> None:
    assert redact_pii("") == ""


def test_redact_non_string_unchanged() -> None:
    assert redact_pii(None) is None  # type: ignore[arg-type]
    assert redact_pii(123) == 123  # type: ignore[arg-type]


def test_redact_clean_text_unchanged() -> None:
    assert redact_pii("普通昵称") == "普通昵称"


# ---------------------------------------------------------------------------
# mask_user_identify — phone masking
# ---------------------------------------------------------------------------


def test_mask_phone_standard() -> None:
    assert mask_user_identify("13800138000") == "138*****000"


def test_mask_phone_all_digits_variants() -> None:
    assert mask_user_identify("19912345678") == "199*****678"
    assert mask_user_identify("15500001234") == "155*****234"


def test_mask_phone_preserves_first3_last3() -> None:
    result = mask_user_identify("13800138000")
    assert result[:3] == "138"
    assert result[-3:] == "000"
    assert "*****" in result


# ---------------------------------------------------------------------------
# mask_user_identify — email masking
# ---------------------------------------------------------------------------


def test_mask_email_standard() -> None:
    assert mask_user_identify("test@example.com") == "te*****@example.com"


def test_mask_email_short_local_part_one_char() -> None:
    result = mask_user_identify("a@example.com")
    assert result.endswith("@example.com")
    assert "*****" in result


def test_mask_email_short_local_part_two_chars() -> None:
    result = mask_user_identify("ab@example.com")
    assert result.startswith("ab")
    assert "*****" in result
    assert result.endswith("@example.com")


def test_mask_email_long_local_part() -> None:
    result = mask_user_identify("longusername@company.org")
    assert result.startswith("lo")
    assert "*****" in result
    assert result.endswith("@company.org")


def test_mask_email_preserves_domain() -> None:
    result = mask_user_identify("user@sub.domain.co.uk")
    assert result.endswith("@sub.domain.co.uk")


# ---------------------------------------------------------------------------
# mask_user_identify — unrecognised / edge cases
# ---------------------------------------------------------------------------


def test_mask_unrecognised_format_returned_unchanged() -> None:
    assert mask_user_identify("something-weird") == "something-weird"


def test_mask_empty_string_unchanged() -> None:
    assert mask_user_identify("") == ""


def test_mask_none_unchanged() -> None:
    assert mask_user_identify(None) is None  # type: ignore[arg-type]


def test_mask_does_not_fully_redact() -> None:
    """Masking must preserve some characters, unlike redact_pii."""
    phone_result = mask_user_identify("13800138000")
    assert phone_result != "[REDACTED-PHONE]"
    assert phone_result != "13800138000"

    email_result = mask_user_identify("test@example.com")
    assert email_result != "[REDACTED-EMAIL]"
    assert email_result != "test@example.com"
