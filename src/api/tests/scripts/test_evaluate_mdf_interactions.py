"""Exercise the local evaluator through its CLI and the real MarkdownFlow engine."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from scripts.evaluate_mdf_interactions import Case, Replay, evaluate_case

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

API_DIR = Path(__file__).resolve().parents[2]
SCRIPT = API_DIR / "scripts" / "evaluate_mdf_interactions.py"
CATALOG = API_DIR / "scripts" / "mdf_interactions" / "cases.json"
QUESTION = "Which example would you like to try?"
OPTIONS = [["Small garden", "garden"], ["City park", "park"]]
CASE_FIELDS = {
    "id",
    "source",
    "course",
    "tags",
    "smoke",
    "teaching_prompt",
    "course_prompt",
    "locale",
    "memory",
    "steps",
    "replay",
    "replay_only",
}
PRIVATE_FIELD = re.compile(
    r"^(?:trace|session|observation|project|user|learner|request|shifu|outline|"
    r"account|progress|generatedblock)(?:id|bid|url)$"
)
PRIVATE_TEXT = re.compile(
    r"(?i)(?:[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|(?<![a-z0-9])(?:[0-9a-f]{16}|[0-9a-f]{32}"
    r"|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    r"|cl[a-z0-9]{22,30})(?![a-z0-9])"
    r"|(?:pk-lf-|sk-lf-|sk-proj-)[a-z0-9-]+"
    r"|(?<![0-9])1[3-9][0-9]{9}(?![0-9]))"
)
URL = re.compile(r"""(?i)\bhttps?://[^\s<>"'\[\](){}]+""")
EXAMPLE_HOSTS = {"example.com", "example.org", "example.net", "example.invalid"}


def _case() -> dict:
    return {
        "id": "garden-choice",
        "source": "synthetic",
        "course": "sample-course",
        "tags": ["single"],
        "locale": "en-US",
        "teaching_prompt": (
            f"Compare two ways to plan an outdoor space.\n\n{QUESTION}\n"
            + "?[{{ "
            + QUESTION
            + " }} Small garden//garden | City park//park]\n"
            "Explain how to start with the learner's chosen example."
        ),
        "steps": [
            {
                "action": "start",
                "expected": {
                    "outcome": "interaction",
                    "question": {
                        "type": "single",
                        "question": QUESTION,
                        "options": OPTIONS,
                        "variable": QUESTION,
                    },
                    "prose_once": [QUESTION],
                    "memory": {},
                },
            },
            {
                "action": "answer",
                "reload": True,
                "expected": {
                    "outcome": "interaction",
                    "question": {"type": "single"},
                    "asked_before": True,
                    "retryable_error": True,
                    "memory": {},
                },
            },
            {
                "action": "answer",
                "values": ["garden"],
                "expected": {
                    "outcome": "finished",
                    "prose_contains": ["Sketch the beds first."],
                    "memory": {QUESTION: "garden"},
                },
            },
        ],
        "replay": [
            {
                "text": QUESTION,
                "calls": [
                    {
                        "name": "interact",
                        "args": {
                            "type": "single",
                            "question": QUESTION,
                            "options": [
                                {"display": display, "value": stored}
                                for display, stored in OPTIONS
                            ],
                        },
                    }
                ],
            },
            {
                "text": "Sketch the beds first.",
                "calls": [{"name": "finish", "args": {"summary": "Planned a garden"}}],
            },
        ],
    }


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # Failing a connection at its entry point lets this test catch accidental network
    # dependencies even on a developer machine with valid credentials and running services.
    bootstrap = """
import runpy
import socket
import sys

def forbidden(*args, **kwargs):
    raise AssertionError("offline evaluator attempted a network connection")

socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
script = sys.argv.pop(1)
sys.argv[0] = script
runpy.run_path(script, run_name="__main__")
"""
    return subprocess.run(
        [sys.executable, "-c", bootstrap, str(SCRIPT), *args],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _write_cases(path: Path, *cases: dict) -> None:
    path.write_text(json.dumps(cases), encoding="utf-8")


def _report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_offline_replay_reloads_pending_question_and_stores_submitted_value(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    _write_cases(cases, _case())

    process = _run("--cases", str(cases), "--repeat", "2", "--json", str(output))

    assert process.returncode == 0, process.stdout + process.stderr
    result = _report(output)
    assert result["mode"] == "offline"
    assert [case["repeat"] for case in result["results"]] == [1, 2]
    for case in result["results"]:
        assert case["case_id"] == "garden-choice"
        assert case["status"] == "first_attempt_pass"
        question, blank_answer, accepted_answer = case["steps"]
        assert "Small garden//garden" in question["question"]["controls"]
        assert blank_answer["outcome"] == "interaction"
        assert blank_answer["memory"] == {}
        assert accepted_answer["memory"] == {QUESTION: "garden"}
        assert "Sketch the beds first." in accepted_answer["prose"]


@pytest.mark.parametrize(
    ("prose", "verdict", "status", "failures"),
    [
        (
            "Pick the outdoor space you want to start with.",
            True,
            "first_attempt_pass",
            [],
        ),
        (
            "Both spaces have interesting features.",
            False,
            "behavior_failure",
            ["step_1.prose_question"],
        ),
        ("", False, "behavior_failure", ["step_1.prose_question"]),
        ("Pick a space.", None, "call_failure", ["step_1.question_judge_call"]),
    ],
)
def test_live_question_checks_visible_meaning_separately_from_binding(
    prose: str, verdict: bool | None, status: str, failures: list[str]
) -> None:
    fixture = _case()
    expected = fixture["steps"][0]["expected"]
    del expected["prose_once"]
    expected["prose_question"] = QUESTION
    expected["replay_prose_once"] = [QUESTION]
    fixture["replay"][0]["text"] = prose
    case = Case.model_validate(fixture)
    judged = []

    def assessment(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = next(
            part for part in messages[-1].parts if isinstance(part, UserPromptPart)
        )
        judged.append(json.loads(prompt.content))
        if verdict is None:
            return ModelResponse(parts=[TextPart("Invalid unstructured result")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"asked": verdict, "reason": "Test judgment"},
                )
            ]
        )

    result = asyncio.run(
        evaluate_case(
            case, Replay(case.replay).model, judge_model=FunctionModel(assessment)
        )
    )

    assert result["steps"][0]["question"]["variable"] == QUESTION
    assert result["status"] == status
    assert result["failures"] == failures
    assert judged == (
        [{"intended_question": QUESTION, "prose": prose}] if prose else []
    )
    assert result["question_judge_requests"] == len(judged)
    assert result["model_requests"] == (2 if verdict is True else 1)


@pytest.mark.parametrize(
    ("problem", "failure"),
    [
        ("memory", "step_3.memory"),
        ("premature_finish", "step_1.outcome"),
        ("fake_control", "step_1.narrated_controls"),
    ],
)
def test_offline_replay_reports_behavior_failures(
    tmp_path: Path, problem: str, failure: str
) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    case = _case()
    if problem == "memory":
        case["steps"][-1]["expected"]["memory"] = {QUESTION: "park"}
    elif problem == "premature_finish":
        case["replay"] = [{"text": QUESTION, "calls": [{"name": "finish", "args": {}}]}]
    else:
        case["replay"] = [{"text": f"{QUESTION}\n?[Small garden | City park]"}]
    _write_cases(cases, case)

    process = _run("--cases", str(cases), "--json", str(output))

    assert process.returncode == 1, process.stdout + process.stderr
    (result,) = _report(output)["results"]
    assert result["status"] == "behavior_failure"
    assert failure in result["failures"]


@pytest.mark.parametrize("question_count", [0, 2], ids=["omitted", "repeated"])
def test_bundled_offline_replay_checks_question_in_prose(
    tmp_path: Path, question_count: int
) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    case = next(case for case in catalog if case["id"] == "lf-course-01")
    expected = case["steps"][0]["expected"]
    question = expected["prose_question"]
    replay = case["replay"][0]
    replaced = "\n\n".join([question] * question_count)
    replay["text"] = replay["text"].replace(question, replaced)
    _write_cases(cases, case)

    process = _run("--cases", str(cases), "--json", str(output))

    assert process.returncode == 1, process.stdout + process.stderr
    (result,) = _report(output)["results"]
    assert result["status"] == "behavior_failure"
    assert result["failures"] == ["step_1.prose_once[0]"]
    assert result["question_judge_requests"] == 0
    (step,) = result["steps"]
    assert step["outcome"] == "interaction"
    assert step["question"]["variable"] == expected["question"]["variable"]


def test_historical_fallback_counts_as_reproduced_failure(tmp_path: Path) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    case = _case()
    control = "?[Small garden | City park]"
    case["steps"] = [case["steps"][0]]
    case["steps"][0]["replay_expected"] = {
        "outcome": "end",
        "narrated_control": control,
        "memory": {},
    }
    case["replay"] = [{"text": f"{QUESTION}\n\n{control}"}]
    _write_cases(cases, case)

    process = _run("--cases", str(cases), "--json", str(output))

    assert process.returncode == 0, process.stdout + process.stderr
    (result,) = _report(output)["results"]
    assert result["status"] == "expected_failure_replayed"
    assert result["steps"][0]["narrated_controls"] == [control]


def test_comparison_accepts_prompt_changes_and_rejects_different_case_selection(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    original = _case()
    _write_cases(cases, original, {**original, "id": "park-choice"})
    args = ["--cases", str(cases)]
    process = _run(*args, "--case", "garden-choice", "--json", str(baseline))
    assert process.returncode == 0, process.stdout + process.stderr
    prior = _report(baseline)
    prior["prompt_sha256"]["system.md"] = "0" * 64
    baseline.write_text(json.dumps(prior), encoding="utf-8")

    comparison = ["--compare", str(baseline), "--json", str(candidate)]
    process = _run(*args, "--case", "garden-choice", *comparison)
    assert process.returncode == 0, process.stdout + process.stderr
    result = _report(candidate)
    assert result["prompt_sha256"] != prior["prompt_sha256"]
    assert result["comparison"]["compatible"]
    assert result["comparison"]["prompt_changed"]

    process = _run(*args, "--case", "park-choice", *comparison)
    assert process.returncode == 2, process.stdout + process.stderr
    result = _report(candidate)
    assert result["comparison"]["compatible"] is False
    assert result["comparison"]["mismatches"]


def test_bundled_smoke_suite_has_twelve_distinct_cases(tmp_path: Path) -> None:
    output = tmp_path / "smoke.json"
    process = _run("--suite", "smoke", "--json", str(output))
    assert process.returncode == 0, process.stdout + process.stderr
    result = _report(output)
    assert len(result["results"]) == 12
    assert len({case["case_id"] for case in result["results"]}) == 12


def _fixture_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            assert not PRIVATE_FIELD.fullmatch(normalized), "Private catalog field"
            yield key
            yield from _fixture_strings(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _fixture_strings(item)


def test_bundled_catalog_limits_provenance_and_private_data() -> None:
    cases = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert cases
    assert {case["source"] for case in cases} <= {"langfuse", "synthetic"}
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert set(case) <= CASE_FIELDS, case["id"]
        if case["source"] == "langfuse":
            assert re.fullmatch(r"course-\d{2}", case["course"]), case["id"]
        for content in _fixture_strings(case):
            assert not PRIVATE_TEXT.search(content), case["id"]
            for url in URL.findall(content):
                hostname = urlsplit(url).hostname or ""
                assert hostname in EXAMPLE_HOSTS, case["id"]


def test_bundled_catalog_covers_trace_diversity_and_replay_anomalies() -> None:
    cases = json.loads(CATALOG.read_text(encoding="utf-8"))
    derived = [case for case in cases if case["source"] == "langfuse"]
    observed_anomalies = [
        case for case in derived if "observed-anomaly" in case["tags"]
    ]
    course_count = len({case["course"] for case in derived})
    assert len(derived) >= 48, f"Only {len(derived)} trace-derived cases"
    assert course_count >= 8, f"Only {course_count} trace-derived courses"
    assert len(observed_anomalies) >= 12, (
        f"Only {len(observed_anomalies)} trace-derived anomalies"
    )
    control_types = {
        expected["question"]["type"]
        for case in cases
        for step in case["steps"]
        if (expected := step["expected"]).get("question")
    }
    assert control_types == {
        "single",
        "multi",
        "text",
        "single_or_text",
        "multi_or_text",
        "confirm",
    }


@pytest.mark.parametrize("allow_queue", [False, True])
def test_offline_replay_checks_question_count_independently_of_pending(
    tmp_path: Path, allow_queue: bool
) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    case = next(case for case in catalog if case["id"] == "queued-choice-reload")
    start = case["steps"][0]["expected"]
    del start["pending"]
    if not allow_queue:
        del start["question_count"]
    _write_cases(cases, case)

    process = _run("--cases", str(cases), "--json", str(output))

    assert process.returncode == (0 if allow_queue else 1), (
        process.stdout + process.stderr
    )
    (result,) = _report(output)["results"]
    assert len(result["steps"][0]["questions"]) == 2
    assert result["failures"] == ([] if allow_queue else ["step_1.question_count"])
