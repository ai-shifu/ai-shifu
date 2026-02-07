import pytest

from flaskr.service.order.admin import parse_import_activation_entries


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
