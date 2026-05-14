"""PII redaction helpers for creator-analytics responses.

Even when a column is in the whitelist, the *content* of the column may
contain personally identifying information (a learner pasted their phone
number into their nickname, an email into a free-form variable value, etc.).
This module provides regex-based redaction applied to user-visible strings
before the response leaves the API surface.

The regexes are deliberately conservative — they only catch the highest-risk,
well-known patterns. We prefer false negatives (some PII slips through) over
false positives (mangling a legitimate nickname like ``"123 abc"``).
"""

from __future__ import annotations

import re


# Mainland China mobile numbers (11 digits, start with 1, second digit 3-9).
# Surrounded by word boundaries to avoid clipping out of order-numbers etc.
_PHONE_CN_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# Common email shape; intentionally narrow to avoid eating "@mention" handles.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Mainland China resident ID number (18 chars: 17 digits + check digit X/digit).
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_pii(text: str) -> str:
    """Return ``text`` with phone / email / ID-card patterns masked out.

    Empty or non-string input is returned unchanged so callers can apply this
    over heterogeneous result rows without type-guarding every value.
    """

    if not isinstance(text, str) or not text:
        return text
    text = _PHONE_CN_RE.sub("[REDACTED-PHONE]", text)
    text = _EMAIL_RE.sub("[REDACTED-EMAIL]", text)
    text = _ID_CARD_RE.sub("[REDACTED-IDCARD]", text)
    return text


# ---------------------------------------------------------------------------
# Masking helpers for dedicated PII fields (user_identify)
# These preserve enough characters to let a creator cross-reference their own
# student list while hiding the full value from casual inspection.
# ---------------------------------------------------------------------------


def _mask_phone(value: str) -> str:
    """Return a masked Chinese phone number: ``138*****000``."""
    return value[:3] + "*****" + value[-3:]


def _mask_email(value: str) -> str:
    """Return a masked email address: ``te*****@example.com``.

    At most the first two characters of the local part are preserved;
    the domain (including ``@``) is kept intact.
    """
    at_idx = value.find("@")
    if at_idx < 0:
        return value
    local = value[:at_idx]
    domain = value[at_idx:]
    prefix = local[:2] if len(local) >= 2 else local
    return prefix + "*****" + domain


def mask_user_identify(value: str) -> str:
    """Return a masked ``user_identify`` value.

    Detects whether the value is a phone number or email and applies the
    appropriate masking.  Unrecognised formats are returned unchanged.
    Empty or non-string values are returned as-is.
    """
    if not isinstance(value, str) or not value:
        return value
    if _PHONE_CN_RE.fullmatch(value):
        return _mask_phone(value)
    if "@" in value:
        return _mask_email(value)
    return value
