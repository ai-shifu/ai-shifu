"""Exercise course import/export against persistent revisions and outline history."""

import json
import uuid
from collections.abc import Iterator
from io import BytesIO
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.shifu import shifu_import_export_funcs as transfers
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
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


def _file(payload: object) -> FileStorage:
    return FileStorage(
        stream=BytesIO(json.dumps(payload).encode()),
        filename="course.json",
        content_type="application/json",
    )


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
