from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_shifu_preview_routes_gate_creator_debug_usage_with_billing_admission() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/route.py").read_text(encoding="utf-8")

    assert "from flaskr.service.billing.admission import admit_creator_usage" in source
    assert "reserve_creator_runtime_slot" not in source
    assert "from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG" in source
    assert "def _admit_creator_debug_usage() -> None:" in source
    assert source.count("_admit_creator_debug_usage()") >= 3
    assert "def ask_preview_api():" in source
    assert "def tts_preview_api():" in source


def test_shifu_ask_preview_routes_pass_debug_usage_context_into_chat_llm() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/route.py").read_text(encoding="utf-8")

    assert "from flaskr.service.metering import UsageContext" in source
    assert 'generation_name="ask_provider_preview"' in source
    assert "usage_context=UsageContext(" in source
    assert "request_user_is_creator=bool(" in source
    assert source.count("usage_scene=BILL_USAGE_SCENE_DEBUG") >= 2


def test_shifu_tts_preview_helper_records_debug_metering() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/tts_preview.py").read_text(
        encoding="utf-8"
    )

    assert (
        "from flaskr.service.metering import UsageContext, record_tts_usage" in source
    )
    assert "request_user_is_creator: bool = False" in source
    assert source.count("record_tts_usage(") >= 2
    assert "usage_scene=BILL_USAGE_SCENE_DEBUG" in source
