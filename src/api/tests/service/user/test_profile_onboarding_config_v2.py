from __future__ import annotations

import pytest


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
    assert result["document_prompt"] == "Ask concise follow-up questions."
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

    with pytest.raises(Exception) as exc_info:
        module.update_profile_onboarding_config(
            app,
            payload=payload,
            operator_user_bid="operator-1",
        )

    assert field in str(exc_info.value)


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

    with pytest.raises(Exception) as exc_info:
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

    assert "document_prompt" in str(exc_info.value)
    assert saved_payloads == []


def test_profile_onboarding_config_rejects_combined_utf8_payload_over_text_limit(
    app, monkeypatch
):
    from flaskr.service.common import profile_onboarding as module

    saved_values: list[str] = []
    monkeypatch.setattr(
        module,
        "add_config",
        lambda _app, _key, value, **_kwargs: saved_values.append(value),
    )
    payload = module.normalize_profile_onboarding_config_payload(
        {"markdownflow": "测" * 22_000}
    )

    with pytest.raises(Exception) as exc_info:
        module.save_profile_onboarding_config_payload(
            app,
            payload,
            updated_by="operator-1",
        )

    assert (
        len(payload["markdownflow"]) < module.PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    )
    assert "profile_onboarding_config" in str(exc_info.value)
    assert saved_values == []


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
