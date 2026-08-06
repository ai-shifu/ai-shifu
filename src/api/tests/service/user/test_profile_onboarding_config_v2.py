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
    assert "allowed_variable_keys" not in result


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
