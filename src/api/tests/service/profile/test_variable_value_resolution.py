from flaskr.service.profile.funcs import _get_latest_variable_value


class _DummyValue:
    def __init__(self, *, key: str, shifu_bid: str, variable_bid: str):
        self.key = key
        self.shifu_bid = shifu_bid
        self.variable_bid = variable_bid


def test_get_latest_variable_value_prefers_variable_bid_match_over_key_match():
    values = [
        _DummyValue(key="k1", shifu_bid="s1", variable_bid="v-other"),
        _DummyValue(key="k-other", shifu_bid="s1", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(
        values,
        variable_key="k1",
        shifu_bid="s1",
        variable_bid="v1",
    )
    assert hit is values[1]


def test_get_latest_variable_value_prefers_shifu_scoped_key_over_global_key():
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v1"),
        _DummyValue(key="k1", shifu_bid="s1", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="s1")
    assert hit is values[1]


def test_get_latest_variable_value_falls_back_to_global_key_when_shifu_missing():
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(values, variable_key="k1", shifu_bid="s1")
    assert hit is values[0]


def test_get_latest_variable_value_global_variable_bid_beats_global_key():
    values = [
        _DummyValue(key="k1", shifu_bid="", variable_bid="v-other"),
        _DummyValue(key="k-other", shifu_bid="", variable_bid="v1"),
    ]

    hit = _get_latest_variable_value(
        values,
        variable_key="k1",
        shifu_bid="s1",
        variable_bid="v1",
    )
    assert hit is values[1]
