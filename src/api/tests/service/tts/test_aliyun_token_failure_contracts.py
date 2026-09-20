"""Verify temporary speech-token validation and lock-safe refresh failures."""

import pytest
from flaskr.api.tts import aliyun_nls_token as nls


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"",
        " ",
        "not JSON",
        123,
        "null",
        "[]",
        {},
        '{"token":"","expire_time":200}',
        '{"token":"test","expire_time":"bad"}',
        '{"token":"test","expire_time":0}',
    ],
)
def test_invalid_cache_entries_do_not_become_usable_tokens(raw: object) -> None:
    assert nls._decode_cache_value(raw) is None
