from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_shifu_preview_routes_gate_creator_debug_usage_with_billing_admission() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/route.py").read_text(encoding="utf-8")

    assert "from flaskr.service.billing.admission import admit_creator_usage" in source
    assert "from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG" in source
    assert "def _admit_creator_debug_usage() -> None:" in source
    assert source.count("_admit_creator_debug_usage()") >= 3
    assert "def ask_preview_api():" in source
    assert "def tts_preview_api():" in source
