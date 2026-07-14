"""Tests for the AutoJsonMixin DTO serialization base."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from flaskr.route.common import fmt
from flaskr.service.common.dto_base import AutoJsonMixin


class ChildDTO(AutoJsonMixin, BaseModel):
    name: str = Field(...)
    count: int = Field(...)


class SampleDTO(AutoJsonMixin, BaseModel):
    text: str = Field(...)
    number: int = Field(...)
    flag: bool = Field(...)
    amount: Optional[Decimal] = Field(default=None)
    happened_at: Optional[datetime] = Field(default=None)
    child: Optional[ChildDTO] = Field(default=None)
    children: List[ChildDTO] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RenamedDTO(AutoJsonMixin, BaseModel):
    __json_key_overrides__ = {"data": "items"}
    __json_exclude__ = frozenset({"internal_state"})

    page: int = Field(...)
    internal_state: int = Field(default=0)
    data: List[str] = Field(default_factory=list)


def test_json_emits_fields_in_declaration_order_with_identity_keys():
    dto = SampleDTO(text="hello", number=7, flag=True)
    payload = dto.__json__()
    assert list(payload.keys()) == [
        "text",
        "number",
        "flag",
        "amount",
        "happened_at",
        "child",
        "children",
        "tags",
    ]
    assert payload["text"] == "hello"
    assert payload["number"] == 7
    assert payload["flag"] is True


def test_int_and_bool_fields_are_coerced_like_hand_written_json():
    dto = SampleDTO(text="x", number=7, flag=True)
    # simulate un-validated assignment, which pydantic allows by default
    object.__setattr__(dto, "number", "9")
    object.__setattr__(dto, "flag", 0)
    payload = dto.__json__()
    assert payload["number"] == 9
    assert payload["flag"] is False


def test_none_decimal_and_datetime_leaves_pass_through_raw():
    naive = datetime(2026, 7, 3, 12, 0, 0)
    dto = SampleDTO(
        text="x",
        number=1,
        flag=False,
        amount=Decimal("12.30"),
        happened_at=naive,
    )
    payload = dto.__json__()
    # leaves stay raw so the fmt() sink keeps owning their string contract
    assert payload["amount"] == Decimal("12.30")
    assert payload["happened_at"] is naive
    assert payload["child"] is None


def test_fmt_sink_serializes_generated_payload():
    aware = datetime(2026, 7, 3, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    dto = SampleDTO(
        text="x",
        number=1,
        flag=False,
        amount=Decimal("12.30"),
        happened_at=aware,
    )
    body = json.dumps(dto.__json__(), default=fmt, ensure_ascii=False)
    data = json.loads(body)
    assert data["amount"] == "12.30"
    assert data["happened_at"] == "2026-07-03T12:00:00Z"
    assert data["happened_at"].endswith("Z")


def test_nested_dto_and_lists_are_serialized_recursively():
    child = ChildDTO(name="a", count=1)
    dto = SampleDTO(
        text="x",
        number=1,
        flag=False,
        child=child,
        children=[child, ChildDTO(name="b", count=2)],
        tags=["t1", "t2"],
    )
    payload = dto.__json__()
    assert payload["child"] == {"name": "a", "count": 1}
    assert payload["children"] == [
        {"name": "a", "count": 1},
        {"name": "b", "count": 2},
    ]
    # plain lists are passed through untouched
    assert payload["tags"] == ["t1", "t2"]


def test_key_overrides_and_exclusions():
    dto = RenamedDTO(page=2, internal_state=5, data=["a", "b"])
    payload = dto.__json__()
    assert payload == {"page": 2, "items": ["a", "b"]}
    assert list(payload.keys()) == ["page", "items"]
    assert "internal_state" not in payload
