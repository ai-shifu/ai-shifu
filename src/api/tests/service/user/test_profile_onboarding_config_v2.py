from __future__ import annotations

import json

import pytest
from flaskr.service.common.models import AppError


def test_profile_onboarding_config_uses_runtime_validation(app, monkeypatch):
    from flaskr.service.common import profile_onboarding as module

    current_config = {
        "enabled": False,
        "markdownflow": "",
        "document_prompt": "",
        "revision": 4,
        "updated_by": "",
        "updated_at": "",
    }
    validated_documents: list[str] = []
    saved_payloads: list[dict] = []

    monkeypatch.setattr(
        module, "load_profile_onboarding_config_payload", lambda: current_config
    )
    monkeypatch.setattr(
        module,
        "validate_profile_onboarding_markdownflow",
        lambda document: validated_documents.append(document) or {"block_count": 2},
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, *, updated_by: saved_payloads.append(payload),
    )

    document = "?[ %{{role}} ...Tell me about your work ]\n\n---\n\nThanks."
    result = module.update_profile_onboarding_config(
        app,
        payload={
            "enabled": True,
            "markdownflow": document,
            "document_prompt": "Ask concise follow-up questions.",
        },
        operator_user_bid="operator-1",
    )

    assert validated_documents == [document]
    assert saved_payloads[0]["revision"] == 5
    assert result["revision"] == 5
    assert result["config_revision"] == 5
    assert result["version"] == 5
    assert result["markdownflow"] == document
    assert result["document_prompt"] == "Ask concise follow-up questions."
    assert saved_payloads[0]["markdownflow"] == document
    assert result["allowed_variable_keys"] == [
        "sys_user_nickname",
        "sys_user_style",
        "sys_user_background",
    ]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"enabled": "false", "markdownflow": "?[Continue]"}, "enabled"),
        ({"enabled": True, "markdownflow": ""}, "markdownflow"),
        ({"enabled": False, "markdownflow": []}, "markdownflow"),
        (
            {
                "enabled": False,
                "markdownflow": "?[Continue]",
                "document_prompt": {},
            },
            "document_prompt",
        ),
    ],
)
def test_profile_onboarding_config_rejects_invalid_types_or_empty_enabled_flow(
    app, monkeypatch, payload, field
):
    from flaskr.service.common import profile_onboarding as module

    monkeypatch.setattr(
        module,
        "load_profile_onboarding_config_payload",
        lambda: module.normalize_profile_onboarding_config_payload({}),
    )

    with pytest.raises(AppError, match=field):
        module.update_profile_onboarding_config(
            app,
            payload=payload,
            operator_user_bid="operator-1",
        )


def test_profile_onboarding_config_rejects_unanswerable_interaction(app, monkeypatch):
    from flaskr.service.common import profile_onboarding as module

    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        module,
        "load_profile_onboarding_config_payload",
        lambda: module.normalize_profile_onboarding_config_payload({}),
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, *, updated_by: saved_payloads.append(payload),
    )

    with pytest.raises(AppError, match="markdownflow"):
        module.update_profile_onboarding_config(
            app,
            payload={"enabled": True, "markdownflow": "?[]"},
            operator_user_bid="operator-1",
        )

    assert saved_payloads == []


def test_profile_onboarding_config_rejects_oversized_document_prompt(app, monkeypatch):
    from flaskr.service.common import profile_onboarding as module

    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        module,
        "load_profile_onboarding_config_payload",
        lambda: module.normalize_profile_onboarding_config_payload({}),
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, *, updated_by: saved_payloads.append(payload),
    )

    with pytest.raises(AppError, match="document_prompt"):
        module.update_profile_onboarding_config(
            app,
            payload={
                "enabled": False,
                "markdownflow": "",
                "document_prompt": "x"
                * (module.PROFILE_ONBOARDING_DOCUMENT_PROMPT_MAX_CODEPOINTS + 1),
            },
            operator_user_bid="operator-1",
        )

    assert saved_payloads == []


def test_profile_onboarding_config_size_limit_uses_exact_serialized_utf8_bytes(
    app, monkeypatch
):
    from flaskr.service.common import profile_onboarding as module

    saved_values: list[str] = []
    monkeypatch.setattr(module, "_now_iso", lambda: "2026-08-16T00:00:00Z")
    monkeypatch.setattr(
        module,
        "add_config",
        lambda _app, _key, value, **_kwargs: saved_values.append(value),
    )
    markdownflow_prefix = "?[Continue]\n\n---\n\n"
    payload = module.build_profile_onboarding_config_payload(
        enabled=False,
        markdownflow=markdownflow_prefix,
        document_prompt="",
        revision=1,
        updated_by="operator-1",
    )
    base_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    remaining_bytes = module.PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES - base_size
    payload["markdownflow"] += "测" * (remaining_bytes // 3)
    payload["markdownflow"] += "x" * (remaining_bytes % 3)

    module.save_profile_onboarding_config_payload(
        app,
        payload,
        updated_by="operator-1",
    )
    oversized_payload = {
        **payload,
        "markdownflow": payload["markdownflow"] + "测",
    }

    with pytest.raises(AppError, match="profile_onboarding_config"):
        module.save_profile_onboarding_config_payload(
            app, oversized_payload, updated_by="operator-1"
        )

    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) == (
        module.PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    )
    assert len(oversized_payload["markdownflow"]) == len(payload["markdownflow"]) + 1
    assert saved_values == [json.dumps(payload, ensure_ascii=False)]


@pytest.mark.parametrize(
    ("payload", "expected_document_prompt"),
    [
        ({"enabled": False, "markdownflow": ""}, "Keep this prompt."),
        (
            {"enabled": False, "markdownflow": "", "document_prompt": ""},
            "",
        ),
    ],
)
def test_profile_onboarding_config_preserves_only_omitted_document_prompt(
    app, monkeypatch, payload, expected_document_prompt
):
    from flaskr.service.common import profile_onboarding as module

    current_config = module.normalize_profile_onboarding_config_payload(
        {
            "enabled": False,
            "markdownflow": "",
            "document_prompt": "Keep this prompt.",
            "revision": 4,
        }
    )
    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        module, "load_profile_onboarding_config_payload", lambda: current_config
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, saved_payload, *, updated_by: saved_payloads.append(saved_payload),
    )

    result = module.update_profile_onboarding_config(
        app,
        payload=payload,
        operator_user_bid="operator-1",
    )

    assert saved_payloads[0]["document_prompt"] == expected_document_prompt
    assert result["document_prompt"] == expected_document_prompt


def test_profile_onboarding_config_reads_legacy_version_as_revision():
    from flaskr.service.common.profile_onboarding import (
        normalize_profile_onboarding_config_payload,
    )

    result = normalize_profile_onboarding_config_payload(
        {
            "enabled": True,
            "markdownflow": "?[Continue]",
            "version": 7,
        }
    )

    assert result["revision"] == 7
