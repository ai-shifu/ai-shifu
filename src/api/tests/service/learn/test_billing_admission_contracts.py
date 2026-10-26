"""Protect billing admission contracts."""

from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_learn_routes_wire_creator_admission_before_billable_entrypoints() -> None:
    source = (_API_ROOT / "flaskr/service/learn/routes.py").read_text(encoding="utf-8")

    assert "from flaskr.service.billing.admission import admit_creator_usage" in source
    assert (
        "from flaskr.service.billing.api import admit_creator_preview_usage" in source
    )
    assert (
        "def _admit_creator_usage_for_shifu(shifu_bid: str, usage_scene: int)" in source
    )
    assert source.count("_admit_creator_usage_for_shifu(") >= 5
    assert "if usage_scene == BILL_USAGE_SCENE_PREVIEW:" in source
    assert "admit_creator_preview_usage(app, shifu_bid=shifu_bid)" in source
    assert '"/shifu/<shifu_bid>/run/<outline_bid>", methods=["PUT"]' in source
    assert '"/shifu/<shifu_bid>/preview/<outline_bid>"' in source
    assert '"/shifu/<shifu_bid>/generated-blocks/<generated_block_bid>/tts"' in source
    assert '"/shifu/<shifu_bid>/tts/preview"' in source
