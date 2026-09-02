"""Verify course imports cannot bypass Gemini Live model contracts."""

from __future__ import annotations

import io
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.learn.live_follow_up_config import GEMINI_LIVE_MODEL_ID
from flaskr.service.shifu.models import DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from werkzeug.datastructures import FileStorage

if TYPE_CHECKING:
    from pathlib import Path


def _import_file(
    *,
    shifu: dict[str, object],
    outlines: list[dict[str, object]] | None = None,
) -> FileStorage:
    payload = {
        "version": "1.0",
        "shifu": {
            "title": "Imported Live course",
            "llm": "gpt-main",
            "ask_llm": "gpt-follow-up",
            **shifu,
        },
        "outline_items": outlines or [],
    }
    return FileStorage(
        stream=io.BytesIO(json.dumps(payload).encode()),
        filename="course.json",
        content_type="application/json",
    )


@pytest.mark.parametrize(
    ("shifu", "outlines"),
    [
        ({"llm": GEMINI_LIVE_MODEL_ID}, []),
        (
            {},
            [
                {
                    "outline_item_bid": "outline-primary-live",
                    "llm": GEMINI_LIVE_MODEL_ID,
                }
            ],
        ),
        (
            {
                "ask_llm": GEMINI_LIVE_MODEL_ID,
                "ask_provider_config": {
                    "provider": "dify",
                    "mode": "provider_only",
                    "config": {"live_voice": "Kore"},
                },
            },
            [],
        ),
        (
            {
                "ask_provider_config": {
                    "provider": "llm",
                    "mode": "provider_then_llm",
                    "config": {"live_voice": "Kore"},
                }
            },
            [
                {
                    "outline_item_bid": "outline-follow-up-live",
                    "ask_llm": GEMINI_LIVE_MODEL_ID,
                }
            ],
        ),
    ],
)
def test_import_rejects_live_primary_or_invalid_provider_contract(
    app: object,
    shifu: dict[str, object],
    outlines: list[dict[str, object]],
) -> None:
    from flaskr.service.shifu import shifu_import_export_funcs as module

    with pytest.raises(AppError):
        module.import_shifu(
            app,
            f"invalid-live-import-{uuid.uuid4().hex[:12]}",
            _import_file(shifu=shifu, outlines=outlines),
            "teacher-1",
        )


def test_import_live_follow_up_defaults_and_persists_official_voice(
    app: object,
    monkeypatch: object,
) -> None:
    from flaskr.service.shifu import shifu_import_export_funcs as module

    shifu_bid = f"valid-live-import-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(
        module,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )

    imported_bid = module.import_shifu(
        app,
        shifu_bid,
        _import_file(shifu={"ask_llm": GEMINI_LIVE_MODEL_ID}),
        "teacher-1",
    )

    with app.app_context():
        imported = DraftShifu.query.filter_by(
            shifu_bid=shifu_bid,
            deleted=0,
        ).one()
        persisted_config = json.loads(imported.ask_provider_config)
        db.session.expunge(imported)

    assert imported_bid == shifu_bid
    assert persisted_config == {
        "provider": "llm",
        "mode": "provider_only",
        "config": {"live_voice": "Kore"},
    }


def test_export_resolves_default_voice_for_legacy_live_draft(
    app: object,
    tmp_path: Path,
) -> None:
    from flaskr.service.shifu import shifu_import_export_funcs as module

    shifu_bid = f"legacy-live-export-{uuid.uuid4().hex[:12]}"
    with app.app_context():
        draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="Legacy Live export",
            llm="gpt-main",
            ask_llm=GEMINI_LIVE_MODEL_ID,
            ask_provider_config="{}",
            created_user_bid="teacher-1",
            updated_user_bid="teacher-1",
        )
        db.session.add(draft)
        db.session.flush()
        db.session.add(
            LogDraftStruct(
                struct_bid=uuid.uuid4().hex,
                shifu_bid=shifu_bid,
                struct=HistoryItem(
                    bid=shifu_bid,
                    id=draft.id,
                    type="shifu",
                    children=[],
                ).to_json(),
            )
        )
        db.session.commit()

    export_path = tmp_path / "live-course.json"
    assert module.export_shifu(app, shifu_bid, str(export_path)) == "success"

    exported = json.loads(export_path.read_text())
    assert exported["shifu"]["ask_provider_config"] == {
        "provider": "llm",
        "mode": "provider_only",
        "config": {"live_voice": "Kore"},
    }
