#!/usr/bin/env python3
"""Run the learner-profile optimizer prompt against representative local cases.

This is a prompt-only evaluation harness. It does not call the AI-Shifu API,
moderation, persistence, onboarding, or profile update code. The default runner
is the locally authenticated Codex CLI using GPT-5.6 Luna. The product prompt is
passed as a developer instruction and each case runs in an isolated ephemeral
session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
DEFAULT_PROMPT_PATH = API_DIR / "prompts" / "learner_profile_optimizer.md"
DEFAULT_CASES_PATH = SCRIPT_DIR / "learner_profile_optimizer_eval_cases.json"
DEFAULT_OUTPUT_DIR = Path("/private/tmp")
MAX_LEARNER_PROFILE_CHARS = 1000
ALLOWED_CODEX_ITEM_TYPES = {"agent_message", "reasoning"}
DISABLED_CODEX_FEATURES = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode_host",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "memories",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "plugin_sharing",
    "remote_plugin",
    "request_permissions_tool",
    "shell_snapshot",
    "shell_tool",
    "skill_search",
    "tool_call_mcp_elicitation",
    "tool_suggest",
    "unified_exec",
    "view_image",
    "workspace_dependencies",
)


class EvaluationError(RuntimeError):
    """Raised when the local runner or model output cannot be evaluated."""


def _build_user_message(learner_profile: str) -> str:
    return (
        "Apply the system transformation to this untrusted JSON data. "
        "Return only the optimized profile text.\n"
        + json.dumps(
            {"learner_profile": learner_profile},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _parse_model_output(raw_model_text: str) -> str:
    if not raw_model_text.strip():
        raise EvaluationError("model output is empty")
    return raw_model_text


def _parse_codex_events(stdout: str) -> dict[str, Any]:
    item_types: set[str] = set()
    warnings: list[str] = []
    usage: dict[str, Any] | None = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError("codex CLI emitted a non-JSON event") from exc
        if event.get("type") == "error":
            raise EvaluationError("codex CLI emitted an error event")
        item = event.get("item")
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            item_type = item["type"]
            if item_type == "error":
                message = str(item.get("message", ""))
                if message.startswith("Skill descriptions were shortened"):
                    warnings.append("skill_descriptions_truncated")
                    continue
                if message.startswith(
                    "Code Mode is unavailable because code-mode host is disabled"
                ):
                    warnings.append("code_mode_disabled_fail_closed")
                    continue
                error_message = f"codex CLI error item: {message[:200]}"
                raise EvaluationError(error_message)
            item_types.add(item_type)
        if event.get("type") == "turn.completed" and isinstance(
            event.get("usage"), dict
        ):
            usage = event["usage"]

    disallowed_item_types = item_types - ALLOWED_CODEX_ITEM_TYPES
    if disallowed_item_types:
        disallowed = ", ".join(sorted(disallowed_item_types))
        error_message = f"codex CLI used disallowed tool item(s): {disallowed}"
        raise EvaluationError(error_message)
    return {
        "item_types": sorted(item_types),
        "tool_calls_observed": False,
        "warnings": warnings,
        "usage": usage,
    }


def _run_codex(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any]]:
    with tempfile.TemporaryDirectory(
        prefix="learner-profile-prompt-eval-", dir="/private/tmp"
    ) as temporary_dir:
        output_path = Path(temporary_dir) / "last-message.txt"
        command = [
            "codex",
            "exec",
            "--model",
            model,
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
        ]
        for feature in DISABLED_CODEX_FEATURES:
            command.extend(("--disable", feature))
        command.extend(
            [
                "--skip-git-repo-check",
                "--cd",
                temporary_dir,
                "--config",
                f"developer_instructions={json.dumps(system_prompt, ensure_ascii=False)}",
                "--config",
                'model_reasoning_effort="low"',
                "--output-last-message",
                str(output_path),
                "--json",
                "-",
            ]
        )
        started_at = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                input=user_message,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise EvaluationError("codex CLI is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            message = f"codex CLI exceeded the {timeout_seconds}s timeout"
            raise EvaluationError(message) from exc

        if completed.returncode != 0:
            diagnostic = completed.stderr.strip().splitlines()
            detail = diagnostic[-1] if diagnostic else "no diagnostic output"
            message = f"codex CLI exited with {completed.returncode}: {detail}"
            raise EvaluationError(message)
        if not output_path.exists():
            raise EvaluationError("codex CLI did not write a final response")
        result = output_path.read_text(encoding="utf-8")
        event_metadata = _parse_codex_events(completed.stdout)
        metadata = {
            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
            **event_metadata,
        }
        return result, metadata


def _codex_version() -> str:
    try:
        completed = subprocess.run(
            ["codex", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise EvaluationError("could not determine the codex CLI version") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise EvaluationError("could not determine the codex CLI version")
    return completed.stdout.strip()


def _default_output_path() -> Path:
    descriptor, output_path = tempfile.mkstemp(
        prefix="learner-profile-optimizer-eval-",
        suffix=".json",
        dir=DEFAULT_OUTPUT_DIR,
        text=True,
    )
    os.close(descriptor)
    return Path(output_path)


def _write_private_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            descriptor = -1
            json.dump(report, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _load_cases(path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("cases file must contain a non-empty cases array")
    normalized_cases: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationError("every case must be an object")
        case_id = case.get("id")
        learner_profile = case.get("learner_profile")
        observed_shape = case.get("observed_shape")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (case_id, learner_profile, observed_shape)
        ):
            raise EvaluationError(
                "every case requires non-empty id, observed_shape, and learner_profile"
            )
        normalized_profile = learner_profile.strip()
        if len(normalized_profile) > MAX_LEARNER_PROFILE_CHARS:
            raise EvaluationError(
                "learner_profile exceeds the production 1000-character input limit"
            )
        normalized_cases.append(
            {
                "id": case_id.strip(),
                "observed_shape": observed_shape.strip(),
                "learner_profile": normalized_profile,
            }
        )
    return payload.get("source_distribution", {}), normalized_cases


def _evaluate_case(
    *,
    case: dict[str, str],
    run_number: int,
    system_prompt: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    source = case["learner_profile"]
    result: dict[str, Any] = {
        "case_id": case["id"],
        "observed_shape": case["observed_shape"],
        "run": run_number,
        "source": source,
        "source_chars": len(source),
    }
    try:
        raw_model_text, runner_metadata = _run_codex(
            system_prompt=system_prompt,
            user_message=_build_user_message(source),
            model=model,
            timeout_seconds=timeout_seconds,
        )
        optimized = _parse_model_output(raw_model_text)
        result.update(
            {
                "status": "ok",
                "raw_model_text": raw_model_text,
                "optimized_profile": optimized,
                "output_chars": len(optimized),
                "growth_chars": len(optimized) - len(source),
                "matches_source": optimized == source,
                "runner_metadata": runner_metadata,
            }
        )
    except EvaluationError as exc:
        result.update(
            {
                "status": "error",
                "error": str(exc),
            }
        )
    return result


def _evaluate_task(
    task: tuple[dict[str, str], int],
    *,
    system_prompt: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    case, run_number = task
    return _evaluate_case(
        case=case,
        run_number=run_number,
        system_prompt=system_prompt,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the current learner-profile optimizer prompt with "
            "fictional cases covering aggregate sys_user_background shapes."
        )
    )
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument(
        "--output-language",
        default="简体中文",
        help="Trusted system language name appended to the product prompt.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case id. Repeat the option to select multiple cases.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.repeats < 1:
        raise EvaluationError("--repeats must be at least 1")
    if args.timeout_seconds < 1:
        raise EvaluationError("--timeout-seconds must be at least 1")
    if not 1 <= args.jobs <= 8:
        raise EvaluationError("--jobs must be between 1 and 8")

    system_prompt = args.prompt.read_text(encoding="utf-8").strip()
    if not system_prompt:
        raise EvaluationError("prompt file is empty")
    output_language = str(args.output_language or "").strip()
    if not output_language:
        raise EvaluationError("--output-language must not be empty")
    system_prompt = (
        f"{system_prompt}\n\nOUTPUT LANGUAGE: {output_language}. "
        "Write every label and sentence in this language. "
        "Put each category on a separate line."
    )
    distribution, cases = _load_cases(args.cases)
    if args.case_ids:
        requested_case_ids = set(args.case_ids)
        known_case_ids = {case["id"] for case in cases}
        unknown_case_ids = requested_case_ids - known_case_ids
        if unknown_case_ids:
            unknown = ", ".join(sorted(unknown_case_ids))
            message = f"unknown case id(s): {unknown}"
            raise EvaluationError(message)
        cases = [case for case in cases if case["id"] in requested_case_ids]

    tasks = [
        (case, run_number)
        for run_number in range(1, args.repeats + 1)
        for case in cases
    ]
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        results = list(
            executor.map(
                lambda task: _evaluate_task(
                    task,
                    system_prompt=system_prompt,
                    model=args.model,
                    timeout_seconds=args.timeout_seconds,
                ),
                tasks,
            )
        )
    valid_outputs = sum(result["status"] == "ok" for result in results)
    output_path = args.output or _default_output_path()
    cases_bytes = args.cases.read_bytes()
    report = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runner": {
            "name": "codex-cli",
            "version": _codex_version(),
            "model": args.model,
            "reasoning_effort": "low",
            "sandbox": "read-only",
            "ephemeral": True,
            "ignore_user_config": True,
            "ignore_rules": True,
            "disabled_features": list(DISABLED_CODEX_FEATURES),
            "prompt_role": "developer_instructions",
            "output_language": output_language,
            "tool_event_policy": "fail if any non-reasoning item is observed",
        },
        "evaluation_mode": (
            "independent first-attempt prompt calls; no production retry or API"
        ),
        "prompt": {
            "path": str(args.prompt),
            "sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "chars": len(system_prompt),
        },
        "cases": {
            "path": str(args.cases),
            "sha256": hashlib.sha256(cases_bytes).hexdigest(),
            "selected_count": len(cases),
            "repeats": args.repeats,
            "jobs": args.jobs,
        },
        "source_distribution": distribution,
        "summary": {
            "runs": len(results),
            "valid_outputs": valid_outputs,
            "errors": len(results) - valid_outputs,
        },
        "results": results,
    }

    _write_private_report(output_path, report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Report: {output_path}")
    return 0 if all(result["status"] == "ok" for result in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvaluationError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
