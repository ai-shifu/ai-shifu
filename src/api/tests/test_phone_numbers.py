from flaskr.service.common.phone_numbers import (
    is_valid_sms_mobile,
    normalize_phone_identifier,
)


def test_normalize_phone_identifier_strips_cn_prefix():
    assert normalize_phone_identifier("+8613800000000") == "13800000000"


def test_is_valid_sms_mobile_accepts_cn_mobile():
    assert is_valid_sms_mobile("13800000000") is True
    assert is_valid_sms_mobile("+8613800000000") is True


def test_is_valid_sms_mobile_rejects_invalid_mobile():
    assert is_valid_sms_mobile("186380295265") is False
    assert is_valid_sms_mobile("23800000000") is False
    assert is_valid_sms_mobile("") is False
