"""Tests for the AutoJsonMixin DTO serialization base."""

import importlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import get_args

import pytest
from flaskr.common.swagger import swagger_config
from flaskr.route.common import fmt
from flaskr.service.common.dto_base import AutoJsonMixin
from flaskr.service.common.dtos import UserInfo, UserToken
from pydantic import BaseModel, Field


class ChildDTO(AutoJsonMixin, BaseModel):
    """Verify child DTO behavior."""

    name: str = Field(...)
    count: int = Field(...)


class SampleDTO(AutoJsonMixin, BaseModel):
    """Verify sample DTO behavior."""

    text: str = Field(...)
    number: int = Field(...)
    flag: bool = Field(...)
    amount: Decimal | None = Field(default=None)
    happened_at: datetime | None = Field(default=None)
    child: ChildDTO | None = Field(default=None)
    children: list[ChildDTO] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RenamedDTO(AutoJsonMixin, BaseModel):
    """Verify renamed DTO behavior."""

    __json_key_overrides__ = {"data": "items"}
    __json_exclude__ = frozenset({"internal_state"})

    page: int = Field(...)
    internal_state: int = Field(default=0)
    data: list[str] = Field(default_factory=list)


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


def test_user_token_keeps_camel_case_wire_and_swagger_field() -> None:
    """Keep the intentional N815 exception aligned with both public contracts."""
    user_info = UserInfo(
        user_id="user-1",
        username="learner",
        name="Learner",
        email="learner@example.com",
        mobile="13800138000",
        user_state=1,
        wx_openid="openid-1",
        language="zh-CN",
    )
    token = UserToken(userInfo=user_info, token="token-1")

    assert token.__json__() == {"userInfo": user_info, "token": "token-1"}
    schema = swagger_config["components"]["schemas"]["UserToken"]
    assert list(schema["properties"]) == ["userInfo", "token"]
    assert schema["required"] == ["userInfo", "token"]


@pytest.mark.parametrize(
    ("module_name", "model_name", "field_name"),
    [
        (
            "flaskr.service.billing.dtos",
            "BillingSubscriptionDTO",
            "current_period_end_at",
        ),
        (
            "flaskr.service.dashboard.dtos",
            "DashboardEntryCourseItemDTO",
            "last_active_at",
        ),
        (
            "flaskr.service.order.admin_dtos",
            "OrderAdminSummaryDTO",
            "created_at",
        ),
        (
            "flaskr.service.shifu.admin_dtos_courses",
            "AdminOperationCourseSummaryDTO",
            "created_at",
        ),
        (
            "flaskr.service.shifu.admin_dtos_users",
            "AdminOperationUserSummaryDTO",
            "created_at",
        ),
    ],
)
def test_pydantic_datetime_fields_keep_runtime_imports(
    module_name: str,
    model_name: str,
    field_name: str,
) -> None:
    """Keep Pydantic field types available while each model class is built."""
    module = importlib.import_module(module_name)
    model = getattr(module, model_name)

    assert module.datetime is datetime
    annotation = model.model_fields[field_name].annotation
    assert annotation is datetime or datetime in get_args(annotation)
