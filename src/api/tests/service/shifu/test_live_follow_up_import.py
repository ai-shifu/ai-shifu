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
    include_structure: bool = False,
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
        "structure": {
            "bid": "old-course",
            "type": "shifu",
            "children": [
                {"bid": item["outline_item_bid"], "type": "outline", "children": []}
                for item in (outlines or [])
            ],
        },
    }
    if include_structure:
        payload["structure"] = {
            "type": "shifu",
            "bid": "import-root",
            "children": [
                {"type": "outline", "bid": item["outline_item_bid"], "children": []}
                for item in outlines or []
            ],
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


@pytest.mark.parametrize("legacy_model", ["old-text-model", GEMINI_LIVE_MODEL_ID])
def test_legacy_outline_models_are_ignored_and_not_exported(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    legacy_model: str,
) -> None:
    from flaskr.service.shifu import shifu_import_export_funcs as module
    from flaskr.service.shifu.models import DraftOutlineItem

    monkeypatch.setattr(module, "check_text_with_risk_control", lambda *_a, **_k: None)
    shifu_bid = uuid.uuid4().hex
    imported_bid = module.import_shifu(
        app,
        shifu_bid,
        _import_file(
            shifu={},
            outlines=[
                {
                    "outline_item_bid": "old-outline",
                    "title": "Legacy lesson",
                    "llm": legacy_model,
                    "ask_llm": legacy_model,
                    "llm_system_prompt": "Keep the teaching prompt",
                    "ask_llm_system_prompt": "Keep the follow-up prompt",
                    "ask_llm_temperature": 0.4,
                    "ask_enabled_status": 5103,
                    "content": "Keep the lesson content",
                }
            ],
        ),
        "teacher-1",
    )
    assert imported_bid == shifu_bid
    with app.app_context():
        outline = DraftOutlineItem.query.filter_by(shifu_bid=shifu_bid).one()
        assert not hasattr(outline, "llm")
        assert not hasattr(outline, "ask_llm")
        assert outline.clone().eq(outline)
        course = DraftShifu.query.filter_by(shifu_bid=shifu_bid).one()
        assert course.ask_provider_config == "{}"
    export_path = tmp_path / "course.json"
    module.export_shifu(app, shifu_bid, str(export_path))
    exported = json.loads(export_path.read_text())
    assert exported["shifu"]["llm"] == "gpt-main"
    assert exported["shifu"]["ask_llm"] == "gpt-follow-up"
    outline_json = exported["outline_items"][0]
    assert "llm" not in outline_json
    assert "ask_llm" not in outline_json
    assert outline_json["llm_system_prompt"] == "Keep the teaching prompt"
    assert outline_json["ask_llm_system_prompt"] == "Keep the follow-up prompt"
    assert "ask_llm_temperature" not in outline_json
    assert outline_json["ask_enabled_status"] == 5103
    assert outline_json["content"] == "Keep the lesson content"
