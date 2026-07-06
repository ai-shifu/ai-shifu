import pytest

from flaskr.service.common.models import AppException
from flaskr.service.shifu.shifu_outline_funcs import (
    convert_outline_to_reorder_outline_item_dto,
)


def test_convert_accepts_nested_outline_tree():
    dtos = convert_outline_to_reorder_outline_item_dto(
        [
            {
                "bid": "root",
                "children": [
                    {"bid": "child", "children": []},
                ],
            }
        ]
    )
    assert [dto.bid for dto in dtos] == ["root"]
    assert [child.bid for child in dtos[0].children] == ["child"]


def test_convert_tolerates_null_children():
    # A leaf node may send "children": null instead of omitting the key; it
    # should be treated as an empty child list rather than raising.
    dtos = convert_outline_to_reorder_outline_item_dto(
        [{"bid": "leaf", "children": None}]
    )
    assert dtos[0].bid == "leaf"
    assert dtos[0].children == []


def test_convert_accepts_empty_list():
    assert convert_outline_to_reorder_outline_item_dto([]) == []


@pytest.mark.parametrize("bad_value", [None, {}, "outlines", 42])
def test_convert_rejects_non_list_top_level(bad_value):
    with pytest.raises(AppException):
        convert_outline_to_reorder_outline_item_dto(bad_value)


@pytest.mark.parametrize("bad_item", ["not-a-dict", 1, ["nested"], None])
def test_convert_rejects_non_dict_items(bad_item):
    with pytest.raises(AppException):
        convert_outline_to_reorder_outline_item_dto([bad_item])
