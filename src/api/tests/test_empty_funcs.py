def func_empty_dict(a, **kwargs):
    return {}


def test_empty_funcs():
    test = {
        "b": 2,
        "c": 3,
    }
    assert func_empty_dict({}) == {}
    assert func_empty_dict(a=2) == {}
    assert func_empty_dict(a=2, **test) == {}
    assert func_empty_dict(a=2, **{}) == {}
    assert func_empty_dict(None) == {}
    assert func_empty_dict(a=1, b=2, c=3) == {}
