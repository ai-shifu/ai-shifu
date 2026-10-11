"""Keep new outline permissions consistent across authoring entry points."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu import route as shifu_routes
from flaskr.service.shifu import shifu_outline_funcs
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_GUEST, UNIT_TYPE_VALUE_TRIAL
from flaskr.service.shifu.dtos import ShifuDetailDto
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu

OWNER = "outline-default-teacher"
HEADERS = {"Token": "outline-default-token"}


@pytest.fixture
def course(
    app: object, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> str:
    """Provide a draft and isolate integrations from permission persistence."""
    shifu_bid = f"outline-default-{request.node.name}"
    user = SimpleNamespace(
        user_id=OWNER, is_creator=True, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)
    monkeypatch.setattr(
        shifu_routes, "shifu_permission_verification", Mock(return_value=True)
    )
    monkeypatch.setattr(shifu_routes, "get_shifu_creator_bid", Mock(return_value=OWNER))
    monkeypatch.setattr(shifu_outline_funcs, "check_text_with_risk_control", Mock())
    monkeypatch.setattr(shifu_outline_funcs, "save_new_outline_history", Mock())
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Outline Defaults",
                created_user_bid=OWNER,
                updated_user_bid=OWNER,
                deleted=0,
            )
        )
    return shifu_bid


def _persisted_type(app: object, course: str, outline_bid: str) -> int:
    with app.app_context():
        outline = DraftOutlineItem.query.filter_by(
            shifu_bid=course, outline_item_bid=outline_bid
        ).one()
        return outline.type


@pytest.mark.parametrize("permission", [{}, {"type": None}])
def test_create_outline_api_defaults_to_free_when_permission_is_missing_or_null(
    app: object, test_client: object, course: str, permission: dict
) -> None:
    response = test_client.put(
        f"/api/shifu/shifus/{course}/outlines",
        headers=HEADERS,
        json={"name": "Lesson", **permission},
    ).get_json(force=True)

    assert response["code"] == 0
    assert response["data"]["type"] == "trial"
    assert (
        _persisted_type(app, course, response["data"]["bid"]) == UNIT_TYPE_VALUE_TRIAL
    )


@pytest.mark.parametrize(
    ("permission", "stored_type"), [("guest", 400), ("trial", 401), ("normal", 402)]
)
def test_create_outline_api_preserves_explicit_permission(
    app: object,
    test_client: object,
    course: str,
    permission: str,
    stored_type: int,
) -> None:
    response = test_client.put(
        f"/api/shifu/shifus/{course}/outlines",
        headers=HEADERS,
        json={"name": "Lesson", "type": permission},
    ).get_json(force=True)

    assert response["code"] == 0
    assert response["data"]["type"] == permission
    assert _persisted_type(app, course, response["data"]["bid"]) == stored_type


def test_create_batch_api_defaults_nested_nodes_and_preserves_explicit_permissions(
    app: object, test_client: object, course: str
) -> None:
    response = test_client.put(
        f"/api/shifu/shifus/{course}/outlines/batch",
        headers=HEADERS,
        json={
            "outlines": [
                {
                    "name": "Chapter",
                    "children": [
                        {"name": "Missing"},
                        {"name": "Null", "type": None},
                        {"name": "Guest", "type": "guest"},
                        {"name": "Free", "type": "trial"},
                        {"name": "Paid", "type": "normal"},
                    ],
                }
            ]
        },
    ).get_json(force=True)

    assert response["code"] == 0
    chapter = response["data"][0]
    nodes = [chapter, *chapter["children"]]
    assert [node["type"] for node in nodes] == [
        "trial",
        "trial",
        "trial",
        "guest",
        "trial",
        "normal",
    ]
    assert [_persisted_type(app, course, node["bid"]) for node in nodes] == [
        401,
        401,
        401,
        400,
        401,
        402,
    ]


def test_direct_creation_defaults_to_free_without_changing_existing_guest(
    app: object, course: str
) -> None:
    guest = shifu_outline_funcs.create_outline(
        app, OWNER, course, "", "Guest lesson", "guest"
    )
    created = shifu_outline_funcs.create_outline(
        app, OWNER, course, "", "Default lesson"
    )

    assert created.type == "trial"
    assert _persisted_type(app, course, created.bid) == UNIT_TYPE_VALUE_TRIAL
    assert _persisted_type(app, course, guest.bid) == UNIT_TYPE_VALUE_GUEST


def test_course_detail_serializes_backend_default_permission() -> None:
    detail = ShifuDetailDto(
        shifu_id="course",
        shifu_name="Course",
        shifu_description="Description",
        shifu_avatar="",
        shifu_keywords=[],
        shifu_model="1",
        shifu_price=0,
        shifu_preview_url="",
        shifu_url="",
        shifu_system_prompt="",
        readonly=False,
        archived=False,
    )

    assert detail.default_learning_permission == "trial"
    assert detail.__json__()["default_learning_permission"] == "trial"
