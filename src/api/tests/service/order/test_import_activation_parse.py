import pytest

from flaskr.service.common.models import AppException
from flaskr.service.order.admin import normalize_mobile, parse_import_activation_entries


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
