"""Focused tests for public onboarding-assistant prompt localization."""

import json
from types import SimpleNamespace

import pytest
from flaskr.api.llm import LLMStreamResponse
from flaskr.service.common.models import AppError

LOCALE_LABELS = {
    "ar-SA": "العربية",
    "en-US": "English",
    "fr-FR": "Français",
    "th-TH": "ไทย",
    "zh-CN": "中文",
}
LOCALIZED_PROMPTS = {
    "ar-SA": "استنادًا إلى ما تعرفه عني، أجب عن السؤال.",
    "en-US": "Based on what you know about me, answer the question.",
    "fr-FR": "D'après ce que tu sais de moi, réponds à la question.",
    "th-TH": "จากสิ่งที่คุณรู้เกี่ยวกับฉัน โปรดตอบคำถาม",
    "zh-CN": "请根据你对我的了解，回答这个问题。",
}


def _completed_response(
    *,
    source_locale: object = "zh-CN",
    assistant_prompts: object = LOCALIZED_PROMPTS,
    complete: object = True,
) -> str:
    return json.dumps(
        {
            "source_locale": source_locale,
            "assistant_prompts": assistant_prompts,
            "complete": complete,
        },
        ensure_ascii=False,
    )


def test_localizer_uses_shared_locale_registry_and_one_llm_call(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    master_prompt = LOCALIZED_PROMPTS["zh-CN"]

    def invoke(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        response = _completed_response()
        midpoint = len(response) // 2
        return [
            SimpleNamespace(result=response[:midpoint]),
            SimpleNamespace(result=response[midpoint:]),
        ]

    monkeypatch.setattr(module, "get_locale_labels", LOCALE_LABELS.copy)
    monkeypatch.setattr(module, "invoke_llm", invoke)

    result = module.localize_profile_onboarding_assistant_prompt(
        app, f" \n{master_prompt}\n "
    )

    assert result == LOCALIZED_PROMPTS
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert json.loads(args[4]) == {
        "assistant_prompt": master_prompt,
        "target_locales": LOCALE_LABELS,
    }
    assert kwargs["json"] is True
    assert kwargs["generation_name"] == "profile_onboarding_assistant_localizer"
    assert '"source_locale", "assistant_prompts", and "complete"' in kwargs["system"]
    assert "exactly one non-empty JSON string" in kwargs["system"]
    assert "exactly, byte for byte" in kwargs["system"]
    assert "first-person message from the learner" in kwargs["system"]


def test_localizer_accepts_source_locale_outside_the_supported_registry(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    locale_labels = {"en-US": "English", "fr-FR": "Français"}
    localized_prompts = {
        "en-US": "Based on what you know about me, answer.",
        "fr-FR": "D'après ce que tu sais de moi, réponds.",
    }
    monkeypatch.setattr(module, "get_locale_labels", lambda: locale_labels)
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                result=_completed_response(
                    source_locale="es-ES", assistant_prompts=localized_prompts
                )
            )
        ],
    )

    assert (
        module.localize_profile_onboarding_assistant_prompt(
            app, "Según lo que sabes de mí, responde."
        )
        == localized_prompts
    )


@pytest.mark.parametrize(
    "assistant_prompts",
    [
        {key: value for key, value in LOCALIZED_PROMPTS.items() if key != "th-TH"},
        {**LOCALIZED_PROMPTS, "es-ES": "Según lo que sabes de mí, responde."},
        {**LOCALIZED_PROMPTS, "fr-FR": " \n\t "},
        {**LOCALIZED_PROMPTS, "zh-CN": f" {LOCALIZED_PROMPTS['zh-CN']}"},
    ],
    ids=["missing-locale", "extra-locale", "blank-prompt", "changed-source"],
)
def test_localizer_rejects_invalid_or_changed_locale_maps(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    assistant_prompts: dict[str, str],
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    monkeypatch.setattr(module, "get_locale_labels", LOCALE_LABELS.copy)
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                result=_completed_response(assistant_prompts=assistant_prompts)
            )
        ],
    )

    with pytest.raises(AppError):
        module.localize_profile_onboarding_assistant_prompt(
            app, LOCALIZED_PROMPTS["zh-CN"]
        )


@pytest.mark.parametrize(
    "output",
    [
        "[]",
        "not JSON",
        json.dumps(
            {"source_locale": "zh-CN", "assistant_prompts": LOCALIZED_PROMPTS},
            ensure_ascii=False,
        ),
        _completed_response(complete=False),
        _completed_response(source_locale=None),
        _completed_response(source_locale="not a locale"),
        json.dumps(
            {
                "source_locale": "zh-CN",
                "assistant_prompts": LOCALIZED_PROMPTS,
                "complete": True,
                "extra": "field",
            },
            ensure_ascii=False,
        ),
        '{"source_locale":"zh-CN","source_locale":"fr-FR",'
        f'"assistant_prompts":{json.dumps(LOCALIZED_PROMPTS, ensure_ascii=False)},'
        '"complete":true}',
    ],
    ids=[
        "array",
        "invalid-json",
        "missing-complete",
        "incomplete",
        "invalid-source-locale",
        "malformed-source-locale",
        "extra-envelope-field",
        "duplicate-envelope-field",
    ],
)
def test_localizer_rejects_invalid_completion_envelopes(
    app: object, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    monkeypatch.setattr(module, "get_locale_labels", LOCALE_LABELS.copy)
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: [SimpleNamespace(result=output)],
    )

    with pytest.raises(AppError):
        module.localize_profile_onboarding_assistant_prompt(
            app, LOCALIZED_PROMPTS["zh-CN"]
        )


@pytest.mark.parametrize("source_locale", ["zh-cn", "zh", "zh-TW"])
def test_localizer_cannot_bypass_source_preservation_with_locale_alias(
    app: object, monkeypatch: pytest.MonkeyPatch, source_locale: str
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    monkeypatch.setattr(module, "get_locale_labels", LOCALE_LABELS.copy)
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                result=_completed_response(
                    source_locale=source_locale,
                    assistant_prompts={
                        **LOCALIZED_PROMPTS,
                        "zh-CN": "被改写的母版",
                    },
                )
            )
        ],
    )

    with pytest.raises(AppError):
        module.localize_profile_onboarding_assistant_prompt(
            app, LOCALIZED_PROMPTS["zh-CN"]
        )


def test_localizer_rejects_an_ambiguous_source_primary_locale(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    locale_labels = {"en-US": "English (US)", "en-GB": "English (UK)"}
    localized_prompts = {
        "en-US": "Answer with what you know about me.",
        "en-GB": "Answer with what you know about me.",
    }
    monkeypatch.setattr(module, "get_locale_labels", lambda: locale_labels)
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                result=_completed_response(
                    source_locale="en",
                    assistant_prompts=localized_prompts,
                )
            )
        ],
    )

    with pytest.raises(AppError):
        module.localize_profile_onboarding_assistant_prompt(
            app, "Answer with what you know about me."
        )


@pytest.mark.parametrize(
    ("finish_reason", "is_truncated"),
    [("length", False), ("content_filter", True), ("stop", True)],
)
def test_localizer_rejects_truncation_after_consuming_the_stream(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    finish_reason: str,
    is_truncated: bool,
) -> None:
    from flaskr.service.common import profile_onboarding_prompt as module

    stream_finished: list[bool] = []

    def invoke(*_args: object, **_kwargs: object) -> object:
        yield LLMStreamResponse(
            response_id="part-1",
            is_end=False,
            is_truncated=False,
            result='{"source_locale":"zh-CN",',
            finish_reason=None,
            usage=None,
        )
        yield LLMStreamResponse(
            response_id="part-2",
            is_end=True,
            is_truncated=is_truncated,
            result="}",
            finish_reason=finish_reason,
            usage=None,
        )
        stream_finished.append(True)

    monkeypatch.setattr(module, "get_locale_labels", LOCALE_LABELS.copy)
    monkeypatch.setattr(module, "invoke_llm", invoke)

    with pytest.raises(AppError):
        module.localize_profile_onboarding_assistant_prompt(
            app, LOCALIZED_PROMPTS["zh-CN"]
        )
    assert stream_finished == [True]
