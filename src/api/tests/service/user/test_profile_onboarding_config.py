"""Verify the versioned profile-onboarding configuration contract."""

from __future__ import annotations

import json

import pytest
from flaskr.service.common.models import AppError


@pytest.fixture(autouse=True)
def stub_compiler(monkeypatch: object) -> None:
    from flaskr.service.common import profile_onboarding as module

    monkeypatch.setattr(
        module,
        "compile_profile_onboarding_assistant_prompt",
        lambda _app, _document: "Answer these questions using only known facts.",
    )


def test_profile_onboarding_config_uses_runtime_validation(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    current_config = {
        "enabled": False,
        "markdownflow": "",
        "revision": 4,
        "updated_by": "",
        "updated_at": "",
    }
    validated_documents: list[str] = []
    saved_payloads: list[dict] = []

    monkeypatch.setattr(
        module,
        "read_profile_onboarding_database",
        lambda _app: json.dumps(current_config),
    )
    monkeypatch.setattr(
        module,
        "validate_profile_onboarding_markdownflow",
        lambda document: validated_documents.append(document) or {"block_count": 2},
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, **_kwargs: saved_payloads.append(payload),
    )

    document = "?[ %{{role}} ...Tell me about your work ]\n\n---\n\nThanks."
    result = module.update_profile_onboarding_config(
        app,
        payload={
            "enabled": True,
            "markdownflow": document,
        },
        operator_user_bid="operator-1",
    )

    assert validated_documents == [document]
    assert saved_payloads[0]["revision"] == 5
    assert result["config_revision"] == 5
    assert result["markdownflow"] == document
    assert "document_prompt" not in result
    assert saved_payloads[0]["markdownflow"] == document
    assert "document_prompt" not in saved_payloads[0]
    assert "revision" not in result
    assert "version" not in result
    assert "allowed_variable_keys" not in result


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"enabled": "false", "markdownflow": "?[Continue]"}, "enabled"),
        ({"enabled": True, "markdownflow": ""}, "markdownflow"),
        ({"enabled": False, "markdownflow": []}, "markdownflow"),
    ],
)
def test_profile_onboarding_config_rejects_invalid_types_or_empty_enabled_flow(
    app: object, monkeypatch: object, payload: object, field: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    monkeypatch.setattr(
        module,
        "read_profile_onboarding_database",
        lambda _app: None,
    )

    with pytest.raises(AppError, match=field):
        module.update_profile_onboarding_config(
            app,
            payload=payload,
            operator_user_bid="operator-1",
        )


def test_profile_onboarding_config_rejects_unanswerable_interaction(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        module,
        "read_profile_onboarding_database",
        lambda _app: None,
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, **_kwargs: saved_payloads.append(payload),
    )

    with pytest.raises(AppError, match="markdownflow"):
        module.update_profile_onboarding_config(
            app,
            payload={"enabled": True, "markdownflow": "?[]"},
            operator_user_bid="operator-1",
        )

    assert saved_payloads == []


def test_profile_onboarding_config_rejects_oversized_button_values(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    saved_payloads: list[dict] = []
    monkeypatch.setattr(
        module,
        "read_profile_onboarding_database",
        lambda _app: None,
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, **_kwargs: saved_payloads.append(payload),
    )

    with pytest.raises(AppError, match="markdownflow"):
        module.update_profile_onboarding_config(
            app,
            payload={
                "enabled": True,
                "markdownflow": f"?[Short//{'x' * 4_001} | Detailed//full]",
            },
            operator_user_bid="operator-1",
        )

    assert saved_payloads == []


def test_profile_onboarding_config_size_limit_uses_exact_serialized_utf8_bytes(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    saved_values: list[str] = []
    monkeypatch.setattr(module, "_now_iso", lambda: "2026-08-16T00:00:00Z")
    monkeypatch.setattr(
        module,
        "publish_profile_onboarding_database",
        lambda _app, *, value, **_kwargs: saved_values.append(value) or False,
    )
    markdownflow_prefix = "?[Continue]\n\n---\n\n"
    payload = module.build_profile_onboarding_config_payload(
        enabled=False,
        markdownflow=markdownflow_prefix,
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


def test_profile_onboarding_config_drops_legacy_document_prompt(
    app: object, monkeypatch: object
) -> None:
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
        module,
        "read_profile_onboarding_database",
        lambda _app: json.dumps(current_config),
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, saved_payload, **_kwargs: saved_payloads.append(saved_payload),
    )

    result = module.update_profile_onboarding_config(
        app,
        payload={"enabled": False, "markdownflow": ""},
        operator_user_bid="operator-1",
    )

    assert "document_prompt" not in current_config
    assert "document_prompt" not in saved_payloads[0]
    assert "document_prompt" not in result


def test_profile_onboarding_config_ignores_legacy_version_alias() -> None:
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

    assert result["revision"] == 0


@pytest.mark.parametrize(
    ("changed", "missing"), [(True, False), (False, True), (False, False)]
)
def test_saved_prompt_is_compiled_only_when_needed(
    app: object, monkeypatch: object, changed: object, missing: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    document = "What helps you learn?\n\n?[...Your answer]"
    current = {
        "markdownflow": document,
        "assistant_prompt": "" if missing else "Public prompt",
        "revision": 8,
    }
    calls = []
    writes = []
    monkeypatch.setattr(
        module, "read_profile_onboarding_database", lambda _app: json.dumps(current)
    )
    monkeypatch.setattr(
        module,
        "compile_profile_onboarding_assistant_prompt",
        lambda _app, doc: calls.append(doc) or "Compiled prompt",
    )
    monkeypatch.setattr(
        module,
        "save_profile_onboarding_config_payload",
        lambda _app, payload, **kwargs: writes.append((payload, kwargs)) or False,
    )
    submitted = document + ("\n\nAnother question?\n\n?[...Answer]" if changed else "")
    response = module.update_profile_onboarding_config(
        app,
        payload={"enabled": True, "markdownflow": submitted},
        operator_user_bid="operator",
    )
    assert calls == ([submitted] if changed or missing else [])
    assert response["assistant_prompt"] == (
        "Compiled prompt" if calls else "Public prompt"
    )
    assert writes[0][0]["assistant_prompt"] == response["assistant_prompt"]
    assert writes[0][1]["expected_value"] == json.dumps(current)


def test_compiler_failure_and_generated_size_never_publish(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as module

    writes = []
    monkeypatch.setattr(module, "read_profile_onboarding_database", lambda _app: None)
    monkeypatch.setattr(
        module,
        "publish_profile_onboarding_database",
        lambda *_args, **kwargs: writes.append(kwargs),
    )

    def fail(*_args: object) -> object:
        message = "provider unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(module, "compile_profile_onboarding_assistant_prompt", fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        module.update_profile_onboarding_config(
            app,
            payload={"enabled": True, "markdownflow": "?[...Answer]"},
            operator_user_bid="operator",
        )
    monkeypatch.setattr(
        module,
        "compile_profile_onboarding_assistant_prompt",
        lambda *_args: "测" * 22000,
    )
    with pytest.raises(AppError, match="profile_onboarding_config"):
        module.update_profile_onboarding_config(
            app,
            payload={"enabled": True, "markdownflow": "?[...Answer]"},
            operator_user_bid="operator",
        )
    assert writes == []


@pytest.mark.parametrize("override", ["environment", "context"])
def test_nonpersistable_config_is_rejected_before_generation(
    app: object, monkeypatch: object, override: object
) -> None:
    from flaskr.service.common import profile_onboarding as module
    from flaskr.service.config import profile_onboarding as persistence

    monkeypatch.setattr(
        persistence, "has_explicit_env_override", lambda _key: override == "environment"
    )
    monkeypatch.setattr(
        persistence, "has_config_override", lambda _key: override == "context"
    )
    calls = []
    monkeypatch.setattr(
        module,
        "compile_profile_onboarding_assistant_prompt",
        lambda *args: calls.append(args),
    )
    with pytest.raises(AppError):
        module.update_profile_onboarding_config(
            app,
            payload={"enabled": True, "markdownflow": "?[...Answer]"},
            operator_user_bid="operator",
        )
    assert calls == []


def test_assistant_prompt_is_readonly_even_for_service_callers(app: object) -> None:
    from flaskr.service.common import profile_onboarding as module

    with pytest.raises(AppError, match="profile_onboarding_config"):
        module.update_profile_onboarding_config(
            app,
            payload={
                "enabled": False,
                "markdownflow": "",
                "assistant_prompt": "injected",
            },
            operator_user_bid="operator",
        )


@pytest.mark.parametrize("result", ["", "provider_error"])
def test_compiler_wraps_empty_and_provider_failures(
    app: object, monkeypatch: object, result: object
) -> None:
    from types import SimpleNamespace

    from flaskr.service.common import profile_onboarding_prompt as module

    def invoke(*_args: object, **_kwargs: object) -> object:
        if result == "provider_error":
            message = "provider unavailable"
            raise RuntimeError(message)
        return [SimpleNamespace(result="")]

    monkeypatch.setattr(module, "invoke_llm", invoke)
    with pytest.raises(AppError):
        module.compile_profile_onboarding_assistant_prompt(app, "?[...Answer]")


def test_compiler_receives_complete_document_without_user_or_ui_language(
    app: object, monkeypatch: object
) -> None:
    from types import SimpleNamespace

    from flaskr.service.common import profile_onboarding_prompt as module

    calls = []

    def invoke(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return [SimpleNamespace(result="Public "), SimpleNamespace(result="prompt")]

    monkeypatch.setattr(module, "invoke_llm", invoke)
    document = (
        "How do you work?\n```\nverbatim source\n```\n?[...Answer without a variable]"
    )
    assert (
        module.compile_profile_onboarding_assistant_prompt(app, document)
        == "Public prompt"
    )
    args, kwargs = calls[0]
    assert json.loads(args[4]) == {"markdownflow": document}
    assert args[1] == ""
    assert "output_language" not in kwargs
    assert "without bound variables" in kwargs["system"]
    assert 'begin exactly\nwith "请根据你对我的了解"' in kwargs["system"]
    assert "Rewrite every extracted question in the first person" in kwargs["system"]
    assert "for other languages, use the equivalent" in kwargs["system"]
