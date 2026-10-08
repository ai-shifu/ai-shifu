"""Verify variable value resolution behavior."""

from flaskr.service.profile.funcs import _get_latest_variable_value


class _DummyValue:
    def __init__(self, *, key: str, shifu_bid: str, variable_bid: str) -> None:
        self.key = key
        self.shifu_bid = shifu_bid
        self.variable_bid = variable_bid


def test_get_latest_variable_value_prefers_key_match_over_non_matching_variable_bid() -> (
    None
):
    values = [
        _DummyValue(key="k1", shifu_bid="s1", variable_bid="v-other"),
        _DummyValue(key="k-other", shifu_bid="s1", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="s1")
    assert hit is values[0]


def test_get_latest_variable_value_prefers_shifu_scoped_key_over_global_key() -> None:
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v1"),
        _DummyValue(key="k1", shifu_bid="s1", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="s1")
    assert hit is values[1]


def test_get_latest_variable_value_does_not_fall_back_to_global_custom_value() -> None:
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="s1")
    assert hit is None


def test_get_latest_variable_value_explicit_global_scope_matches_registered_field() -> (
    None
):
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v-other"),
        _DummyValue(key="k-other", shifu_bid="", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="")
    assert hit is values[0]
