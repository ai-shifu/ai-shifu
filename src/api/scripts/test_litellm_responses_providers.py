#!/usr/bin/env python3
"""
Smoke test LiteLLM Responses API across all configured providers.

Intended to run inside the ai-shifu-api-dev container where provider env/config
is already present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import litellm


@dataclass
class TestResult:
    provider: str
    display_model: str
    invoke_model: str
    ok: bool
    latency_ms: int
    output_text: str
    finish_reason: str
    usage: Optional[Dict[str, int]]
    input_cache_tokens: int
    error: str


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _usage_to_dict(usage_obj: Any) -> Optional[Dict[str, int]]:
    if not usage_obj:
        return None
    if isinstance(usage_obj, dict):
        usage = usage_obj
    else:
        usage = usage_obj.__dict__ if hasattr(usage_obj, "__dict__") else {}

    def _int(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    out: Dict[str, int] = {}
    for key in ("input", "output", "total"):
        if key in usage:
            out[key] = _int(usage.get(key))
    # Responses shape
    if not out:
        out = {
            "input": _int(usage.get("input_tokens")),
            "output": _int(usage.get("output_tokens")),
            "total": _int(usage.get("total_tokens")),
        }
    if not any(out.values()):
        return None
    out.setdefault("total", out.get("input", 0) + out.get("output", 0))
    return out


def _contains_ok(output_text: str) -> bool:
    text = output_text.strip().lower()
    # Be tolerant to provider formatting differences like `OK.` / `"OK"` / `OK\n`.
    text = text.strip(" \t\r\n\"'`")
    text = text.rstrip(".!。！")
    return text == "ok" or text.startswith("ok")


def _select_models_for_provider(
    provider_models: List[str],
    *,
    allowed_models: List[str],
    all_models: bool,
    per_provider: int,
) -> List[str]:
    if all_models:
        return list(provider_models)

    selected: List[str] = []
    if allowed_models:
        for model in allowed_models:
            if model in provider_models and model not in selected:
                selected.append(model)
            if len(selected) >= per_provider:
                return selected

    for model in provider_models:
        if model not in selected:
            selected.append(model)
        if len(selected) >= per_provider:
            break
    return selected


def _run_stream_test(
    *,
    provider: str,
    display_model: str,
    invoke_model: str,
    params: Dict[str, str],
    reload_params,
    temperature: float,
    max_output_tokens: int,
    timeout: int,
    debug: bool,
) -> TestResult:
    kwargs: Dict[str, Any] = {
        "temperature": float(temperature),
        "max_output_tokens": int(max_output_tokens),
        "timeout": int(timeout),
    }
    if reload_params:
        try:
            kwargs.update(reload_params(display_model, float(temperature)))
        except Exception:
            # Reload params are best-effort; do not block the smoke test.
            pass

    messages = [
        {
            "role": "user",
            "content": "Reply with exactly: OK",
        }
    ]

    if debug:
        litellm.set_verbose = True
        litellm.suppress_debug_info = False

    output_text = ""
    finish_reason = ""
    usage_obj = None
    input_cache_tokens = 0
    error = ""
    start = time.monotonic()
    try:
        # Import here so the module is available inside the container.
        from flaskr.api import llm as llm_module

        stream = litellm.responses(
            model=invoke_model,
            input=messages,
            stream=True,
            **params,
            **kwargs,
        )
        for event in stream:
            (
                delta_text,
                parsed_finish_reason,
                raw_usage,
                _event_id,
                is_terminal,
                error_message,
            ) = llm_module._parse_litellm_stream_event(event)

            if error_message:
                error = _as_str(error_message)
                break

            if raw_usage:
                input_cache_tokens = llm_module._extract_input_cache(raw_usage)
                converted = llm_module._to_langfuse_usage(raw_usage)
                if converted is not None:
                    usage_obj = converted
                else:
                    usage_obj = raw_usage

            if delta_text:
                output_text += _as_str(delta_text)

            if is_terminal and parsed_finish_reason:
                finish_reason = _as_str(parsed_finish_reason)
                break
    except Exception as exc:
        error = _as_str(exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    ok = bool(output_text) and not error and _contains_ok(output_text)
    usage = _usage_to_dict(usage_obj)
    return TestResult(
        provider=provider,
        display_model=display_model,
        invoke_model=invoke_model,
        ok=ok,
        latency_ms=latency_ms,
        output_text=output_text,
        finish_reason=finish_reason,
        usage=usage,
        input_cache_tokens=input_cache_tokens,
        error=error,
    )


def main(argv: List[str]) -> int:
    # Ensure the API project root (where `app.py` lives) is importable even when
    # this script is executed as `python scripts/...`.
    api_root = Path(__file__).resolve().parents[1]
    api_root_str = str(api_root)
    # Always prefer the local `app.py` over any third-party `app` package.
    if sys.path[:1] != [api_root_str]:
        sys.path.insert(0, api_root_str)

    parser = argparse.ArgumentParser(
        description="Smoke test LiteLLM Responses API across configured providers."
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated provider keys to test (default: all enabled).",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated display model names to test (overrides per-provider selection).",
    )
    parser.add_argument(
        "--per-provider",
        type=int,
        default=1,
        help="How many models to test per provider (default: 1).",
    )
    parser.add_argument(
        "--all-models",
        action="store_true",
        help="Test every discovered model for each provider (can be expensive).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0). Provider reload_params may override.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=32,
        help="Clamp max output tokens for the smoke test (default: 32).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-request timeout seconds (default: 60).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON lines.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable LiteLLM verbose logging.",
    )
    args = parser.parse_args(argv)

    # Ensure Flask app + db are initialized before importing modules that depend on SQLAlchemy models.
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    _app = create_app()

    # Import after args/app init to avoid doing provider discovery on --help.
    from flaskr.api import llm as llm_module

    allowed_models = llm_module.get_allowed_models() or []
    provider_filter = [
        item.strip() for item in args.providers.split(",") if item.strip()
    ]
    model_filter = [item.strip() for item in args.models.split(",") if item.strip()]

    results: List[TestResult] = []
    failures: List[TestResult] = []
    skipped: List[Tuple[str, str]] = []

    provider_states = llm_module.PROVIDER_STATES
    provider_keys = list(provider_states.keys())
    if provider_filter:
        provider_keys = [k for k in provider_keys if k in set(provider_filter)]

    # Resolve explicit model list (if provided).
    explicit_tests: List[Tuple[str, str]] = []
    if model_filter:
        for display_model in model_filter:
            provider_key, _normalized = llm_module._resolve_provider_for_model(
                display_model
            )
            explicit_tests.append((provider_key or "", display_model))

    for provider_key in provider_keys:
        state = provider_states.get(provider_key)
        if not state or not state.enabled or not state.params:
            skipped.append((provider_key, "not configured/enabled"))
            continue

        provider_models = list(state.models or [])
        if not provider_models and not explicit_tests:
            skipped.append((provider_key, "no models discovered"))
            continue

        display_models: List[str]
        if explicit_tests:
            display_models = [
                m for p, m in explicit_tests if (not p or p == provider_key)
            ]
            if not display_models:
                # Explicit list does not include this provider.
                continue
        else:
            display_models = _select_models_for_provider(
                provider_models,
                allowed_models=allowed_models,
                all_models=bool(args.all_models),
                per_provider=int(args.per_provider),
            )

        for display_model in display_models:
            try:
                params, invoke_model, reload_params = (
                    llm_module.get_litellm_params_and_model(display_model)
                )
                if not params:
                    skipped.append(
                        (provider_key, f"missing params for {display_model}")
                    )
                    continue
            except Exception as exc:
                result = TestResult(
                    provider=provider_key,
                    display_model=display_model,
                    invoke_model="",
                    ok=False,
                    latency_ms=0,
                    output_text="",
                    finish_reason="",
                    usage=None,
                    input_cache_tokens=0,
                    error=_as_str(exc),
                )
                results.append(result)
                failures.append(result)
                continue

            result = _run_stream_test(
                provider=provider_key,
                display_model=display_model,
                invoke_model=invoke_model,
                params=params,
                reload_params=reload_params,
                temperature=float(args.temperature),
                max_output_tokens=int(args.max_output_tokens),
                timeout=int(args.timeout),
                debug=bool(args.debug),
            )
            results.append(result)
            if not result.ok:
                failures.append(result)

            if args.json:
                print(json.dumps(result.__dict__, ensure_ascii=True))
            else:
                status = "PASS" if result.ok else "FAIL"
                usage_str = ""
                if result.usage:
                    usage_str = (
                        f" usage(input={result.usage.get('input', 0)},"
                        f" output={result.usage.get('output', 0)},"
                        f" total={result.usage.get('total', 0)})"
                    )
                err_str = f" error={result.error}" if result.error else ""
                text_preview = result.output_text.strip().replace("\n", "\\n")[:80]
                print(
                    f"[{status}] provider={provider_key} model={display_model}"
                    f" latency_ms={result.latency_ms} text={text_preview!r}{usage_str}{err_str}"
                )

    if not args.json and skipped:
        for provider_key, reason in skipped:
            print(f"[SKIP] provider={provider_key} reason={reason}")

    if failures:
        if not args.json:
            print(
                f"FAILED providers/models: {len(failures)}/{len(results)}",
                file=sys.stderr,
            )
        return 1

    if not args.json:
        print(f"ALL PASSED: {len(results)}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
