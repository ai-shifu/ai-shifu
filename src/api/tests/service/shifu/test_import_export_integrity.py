"""Exercise course import/export against persistent revisions and outline history."""

import json
import uuid
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import shifu_import_export_funcs as transfers
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import get_shifu_history
from werkzeug.datastructures import FileStorage


@pytest.fixture
def import_owner(app: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    owner = uuid.uuid4().hex
    monkeypatch.setattr(transfers, "check_text_with_risk_control", Mock())
    yield owner
    with app.app_context(), unit_of_work():
        bids = [
            row[0]
            for row in db.session.query(DraftShifu.shifu_bid)
            .filter(DraftShifu.created_user_bid == owner)
            .all()
        ]
        if bids:
            LogDraftStruct.query.filter(LogDraftStruct.shifu_bid.in_(bids)).delete(
                synchronize_session=False
            )
            DraftOutlineItem.query.filter(DraftOutlineItem.shifu_bid.in_(bids)).delete(
                synchronize_session=False
            )
            DraftShifu.query.filter(DraftShifu.shifu_bid.in_(bids)).delete(
                synchronize_session=False
            )


def _payload() -> dict:
    return {
        "version": "1.0",
        "shifu": {
            "shifu_bid": "original",
            "title": "Imported course",
            "llm": "text-model",
            "ask_llm": "ask-model",
            "llm_temperature": 0.7,
            "price": 12.34,
            "llm_system_prompt": "Course prompt",
            "ask_llm_system_prompt": "Question prompt",
        },
        "outline_items": [
            {
                "outline_item_bid": "chapter",
                "title": "Chapter",
                "parent_bid": "",
                "position": "1",
                "llm_system_prompt": "Chapter instruction",
                "content": "",
            },
            {
                "outline_item_bid": "first",
                "title": "First lesson",
                "parent_bid": "chapter",
                "position": "1.1",
                "content": "First teaching block",
            },
            {
                "outline_item_bid": "second",
                "title": "Second lesson",
                "parent_bid": "chapter",
                "position": "1.2",
                "prerequisite_item_bids": " first, missing ",
                "hidden": 1,
                "content": "Second teaching block",
            },
        ],
        "structure": {
            "bid": "original",
            "id": 1,
            "type": "shifu",
            "children": [
                {
                    "bid": "chapter",
                    "id": 2,
                    "type": "outline",
                    "children": [
                        {"bid": "first", "id": 3, "type": "outline", "children": []},
                        {"bid": "second", "id": 4, "type": "outline", "children": []},
                        {"bid": "missing", "id": 5, "type": "outline", "children": []},
                    ],
                },
            ],
        },
    }


def _file(payload: object) -> FileStorage:
    return FileStorage(
        stream=BytesIO(json.dumps(payload).encode()),
        filename="course.json",
        content_type="application/json",
    )


def test_import_remaps_relationships_and_exports_only_the_persisted_history_tree(
    app: object,
    import_owner: str,
    tmp_path: Path,
) -> None:
    bid = transfers.import_shifu(app, None, _file(_payload()), import_owner)
    with app.app_context():
        course = DraftShifu.query.filter_by(shifu_bid=bid).one()
        outlines = {
            row.title: row
            for row in DraftOutlineItem.query.filter_by(shifu_bid=bid, deleted=0).all()
        }
        chapter, first, second = [
            outlines[name] for name in ("Chapter", "First lesson", "Second lesson")
        ]
        assert bid != "original"
        assert first.parent_bid == second.parent_bid == chapter.outline_item_bid
        assert second.prerequisite_item_bids == first.outline_item_bid
        assert chapter.llm_system_prompt == "Chapter instruction"
        history = get_shifu_history(app, bid)
        assert history.bid == bid
        assert history.id == course.id
        assert [item.bid for item in history.children[0].children] == [
            first.outline_item_bid,
            second.outline_item_bid,
        ]
        assert [item.child_count for item in history.children[0].children] == [1, 1]
        active_bids = {row.outline_item_bid for row in outlines.values()}

    target = tmp_path / "nested" / "course.json"
    assert transfers.export_shifu(app, bid, str(target)) == "success"
    exported = json.loads(target.read_text())
    assert exported["version"] == "1.0"
    assert exported["exported_at"].endswith("Z")
    assert exported["shifu"]["price"] == 12.34
    assert exported["shifu"]["llm_system_prompt"] == "Course prompt"
    assert {
        item["outline_item_bid"] for item in exported["outline_items"]
    } == active_bids
    second_export = next(
        item for item in exported["outline_items"] if item["title"] == "Second lesson"
    )
    assert second_export["hidden"] == 1
    assert second_export["prerequisite_item_bids"] in active_bids


def test_reimport_creates_a_course_revision_and_replaces_active_outlines(
    app: object,
    import_owner: str,
    tmp_path: Path,
) -> None:
    bid = transfers.import_shifu(app, uuid.uuid4().hex, _file(_payload()), import_owner)
    with app.app_context():
        initial = DraftShifu.query.filter_by(shifu_bid=bid).one()
        initial_id = initial.id
        initial_outline_ids = [
            row.id for row in DraftOutlineItem.query.filter_by(shifu_bid=bid).all()
        ]
    replacement = _payload()
    replacement["shifu"].update(
        title="Updated course",
        keywords="keyword",
        description="Updated",
        avatar_res_bid="avatar",
        flow_engine=2,
        ask_llm_temperature=0.4,
    )
    assert transfers.import_shifu(app, bid, _file(replacement), import_owner) == bid
    with app.app_context():
        revisions = (
            DraftShifu.query.filter_by(shifu_bid=bid).order_by(DraftShifu.id).all()
        )
        assert [row.title for row in revisions] == ["Imported course", "Updated course"]
        assert revisions[0].id == initial_id
        assert revisions[-1].flow_engine == 2
        assert revisions[-1].updated_user_bid == import_owner
        old_rows = DraftOutlineItem.query.filter(
            DraftOutlineItem.id.in_(initial_outline_ids)
        ).all()
        assert all(row.deleted == 1 for row in old_rows)
        assert DraftOutlineItem.query.filter_by(shifu_bid=bid, deleted=0).count() == 3
    target = tmp_path / "updated.json"
    transfers.export_shifu(app, bid, str(target))
    assert json.loads(target.read_text())["shifu"]["title"] == "Updated course"


def test_risk_rejection_rolls_back_new_revision_outline_deletions_and_history(
    app: object,
    import_owner: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bid = transfers.import_shifu(app, None, _file(_payload()), import_owner)
    with app.app_context():
        history_count = LogDraftStruct.query.filter_by(shifu_bid=bid).count()
    rejection = AppError("Rejected content", status_code=400)
    monkeypatch.setattr(
        transfers, "check_text_with_risk_control", Mock(side_effect=[None, rejection])
    )
    replacement = _payload()
    replacement["shifu"]["title"] = "Rejected replacement"
    with pytest.raises(AppError, match="Rejected content"):
        transfers.import_shifu(app, bid, _file(replacement), import_owner)
    with app.app_context():
        assert (
            DraftShifu.query.filter_by(shifu_bid=bid).one().title == "Imported course"
        )
        assert DraftOutlineItem.query.filter_by(shifu_bid=bid, deleted=0).count() == 3
        assert LogDraftStruct.query.filter_by(shifu_bid=bid).count() == history_count


@pytest.mark.parametrize(
    "payload",
    [
        None,
        12,
        [],
        {},
        {"shifu": {}},
        {"shifu": [], "outline_items": []},
        {"shifu": {}, "outline_items": {}},
        {"shifu": {}, "outline_items": [None]},
    ],
)
def test_import_rejects_invalid_document_shapes_without_creating_a_course(
    app: object,
    import_owner: str,
    payload: object,
) -> None:
    with pytest.raises(AppError):
        transfers.import_shifu(app, None, _file(payload), import_owner)
    with app.app_context():
        assert DraftShifu.query.filter_by(created_user_bid=import_owner).count() == 0


@pytest.mark.parametrize("content", [b"{broken", b"\xff\xfe"])
def test_import_rejects_invalid_json_and_encoding(
    app: object, import_owner: str, content: bytes
) -> None:
    uploaded = FileStorage(stream=BytesIO(content), filename="course.json")
    with pytest.raises(AppError):
        transfers.import_shifu(app, None, uploaded, import_owner)


def test_export_rejects_missing_courses_without_creating_an_output(
    app: object, tmp_path: Path
) -> None:
    target = tmp_path / "missing.json"
    with pytest.raises(AppError) as error:
        transfers.export_shifu(app, uuid.uuid4().hex, str(target))
    assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
    assert not target.exists()


@pytest.mark.parametrize("invalid_field", ["model", "provider", "mode", "live_voice"])
def test_export_rejects_incompatible_live_configuration(
    app: object,
    import_owner: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_field: str,
) -> None:
    bid = transfers.import_shifu(app, None, _file(_payload()), import_owner)
    monkeypatch.setattr(
        transfers,
        "normalize_live_follow_up_course_config",
        lambda **_kwargs: ({}, invalid_field),
    )
    target = tmp_path / "invalid.json"
    with pytest.raises(AppError) as error:
        transfers.export_shifu(app, bid, str(target))
    assert error.value.code == ERROR_CODE["server.common.paramsError"]
    assert not target.exists()
