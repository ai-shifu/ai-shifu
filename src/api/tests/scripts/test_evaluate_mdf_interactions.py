"""Exercise the local evaluator through its CLI and the real MarkdownFlow engine."""

from __future__ import annotations

import asyncio
import io
import json
import re
import subprocess
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from scripts.evaluate_mdf_interactions import (
    Case,
    ObservedModel,
    Replay,
    evaluate_case,
    main,
    repeated_visible_question,
)
from scripts.mdf_interaction_review import main as review_main

from scripts import mdf_interaction_live

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

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


def _review_payload(page: str) -> dict:
    payload = re.search(
        r'<script type="application/json" id="payload">(.*?)</script>', page
    )
    assert payload is not None
    return json.loads(payload[1])


def test_offline_replay_reloads_pending_question_and_stores_submitted_value(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    _write_cases(cases, _case())

    process = _run("--cases", str(cases), "--repeat", "2", "--json", str(output))

    assert process.returncode == 0, process.stdout + process.stderr
    result = _report(output)
    page = output.with_suffix(".review.html").read_text(encoding="utf-8")
    payload = _review_payload(page)
    assert payload["runs"][0]["id"] == result["run_id"]
    assert payload["context"]["garden-choice"]["steps"][2]["values"] == ["garden"]
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
        assert accepted_answer["memory_before"] == {}
        assert "Sketch the beds first." in accepted_answer["prose"]


@pytest.mark.parametrize(
    ("prose", "verdict", "criterion", "status", "failures"),
    [
        (
            "Pick the outdoor space you want to start with.",
            True,
            "passed",
            "first_attempt_pass",
            [],
        ),
        (
            "Both spaces have interesting features.",
            False,
            "failed",
            "behavior_failure",
            ["step_1.prose_question"],
        ),
        ("", False, "failed", "behavior_failure", ["step_1.prose_question"]),
        (
            "Pick a space.",
            None,
            "not_evaluated",
            "call_failure",
            ["step_1.question_judge_call"],
        ),
        (
            "Pick the outdoor space you want to start with.",
            True,
            "passed",
            "behavior_failure",
            ["step_1.question.options"],
        ),
    ],
)
def test_live_question_checks_visible_meaning_separately_from_binding(
    prose: str,
    verdict: bool | None,
    criterion: str,
    status: str,
    failures: list[str],
) -> None:
    fixture = _case()
    expected = fixture["steps"][0]["expected"]
    del expected["prose_once"]
    expected["prose_question"] = QUESTION
    expected["replay_prose_once"] = [QUESTION]
    if "step_1.question.options" in failures:
        expected["question"]["options"] = [["Another park", "other"]]
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
    assert result["steps"][0]["criteria"]["question.variable"] == "passed"
    assert result["steps"][0]["criteria"]["prose_question"] == criterion
    assert result["status"] == status
    assert result["failures"] == failures
    assert judged == (
        [{"intended_question": QUESTION, "prose": prose, "previous_question": None}]
        if prose
        else []
    )
    assert result["question_judge_requests"] == len(judged)
    assert result["model_requests"] == (2 if status == "first_attempt_pass" else 1)


@pytest.mark.parametrize(
    ("verdicts", "control_failure", "encoding"),
    [
        ((None,), False, None),
        ((None,), False, "cp1252"),
        ((True, False), False, None),
        ((True, False), True, None),
    ],
    ids=[
        "inconclusive",
        "strict-stdout",
        "judges-disagree",
        "disagreement-plus-control-failure",
    ],
)
@pytest.mark.parametrize(
    ("criterion", "intent_key", "verdict_key"),
    [
        ("prose_question", "intended_question", "asked"),
        ("prose_meaning", "required_meaning", "covered"),
    ],
)
def test_live_cli_surfaces_unresolved_judgments_with_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verdicts: tuple[bool | None, ...],
    control_failure: bool,
    encoding: str | None,
    criterion: str,
    intent_key: str,
    verdict_key: str,
) -> None:
    fixture = _case()
    expected = fixture["steps"][0]["expected"]
    del expected["prose_once"]
    intent = QUESTION if criterion == "prose_question" else "Choose an outdoor space."
    expected[criterion] = intent
    if control_failure:
        expected["question"]["options"] = [["Another park", "other"]]
    prose = (
        "请先考虑观察地点。"
        if encoding
        else "A small garden or a city park could work. Think about the size."
    )
    fixture["replay"][0]["text"] = prose
    case = Case.model_validate(fixture)
    cases = tmp_path / "cases.json"
    output = tmp_path / "live.json"
    _write_cases(cases, fixture)

    def judge_model(name: str, verdict: bool | None) -> FunctionModel:
        def assessment(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        {verdict_key: verdict, "reason": f"Reading from {name}"},
                    )
                ]
            )

        return FunctionModel(assessment, model_name=name)

    judge_names = ["question-judge", "second-judge"][: len(verdicts)]
    models = {
        name: judge_model(name, verdict)
        for name, verdict in zip(judge_names, verdicts, strict=True)
    }

    @contextmanager
    def build_model(model_id: str) -> Iterator[FunctionModel]:
        yield Replay(case.replay).model if model_id == "teacher" else models[model_id]

    monkeypatch.setattr(mdf_interaction_live, "build_live_model", build_model)
    args = [
        "--cases",
        str(cases),
        "--json",
        str(output),
        "--live",
        "--model",
        "teacher",
        "--judge-model",
        "question-judge",
    ]
    if len(verdicts) == 2:
        args.extend(["--second-judge-model", "second-judge"])
    if encoding:
        buffer = io.BytesIO()
        with io.TextIOWrapper(buffer, encoding=encoding, errors="strict") as terminal:
            with redirect_stdout(terminal):
                assert main(args) == 3
            terminal.flush()
            stdout = buffer.getvalue().decode(encoding)
        assert (
            prose.encode(encoding, errors="backslashreplace").decode(encoding) in stdout
        )
    else:
        assert main(args) == (1 if control_failure else 3)
        stdout = capsys.readouterr().out
        assert prose in stdout

    report = _report(output)
    (result,) = report["results"]
    if control_failure:
        assert result["status"] == "behavior_failure"
        assert result["failures"] == ["step_1.question.options"]
    else:
        assert result["status"] == "needs_review"
        assert result["failures"] == []
        assert result["steps"][-1]["outcome"] == "finished"
    assert result["question_judge_requests"] == len(verdicts)
    assert report["criteria_summary"][criterion] == {
        "passed": 0,
        "failed": 0,
        "needs_review": 1,
        "not_evaluated": 0,
    }
    (review,) = report["review_items"]
    assert (
        review["case_id"],
        review["repeat"],
        review["stage"],
        review["criterion"],
    ) == (
        "garden-choice",
        1,
        1,
        criterion,
    )
    assert review["learner_prose"] == prose
    assert review[intent_key] == intent
    assert [decision["model"] for decision in review["decisions"]] == judge_names
    assert [decision[verdict_key] for decision in review["decisions"]] == list(verdicts)
    reason_marker = "disagree" if len(verdicts) == 2 else "ambiguous"
    assert reason_marker in review["reason"]
    assert "Criterion assessment" in stdout
    assert "Items needing human review: 1" in stdout


@pytest.mark.parametrize(
    ("case_id", "response_index", "stage", "criterion", "prose", "verdict"),
    [
        (
            "lf-empty-pause-01",
            0,
            1,
            "prose_meaning",
            "合上盒盖前，先把拆下的垫片放进标记好的小袋里。",
            True,
        ),
        (
            "lf-empty-pause-01",
            0,
            1,
            "prose_meaning",
            "合上盒盖前把拆下的垫片装进标记好的小袋。请核对袋子里垫片放齐没有。",
            False,
        ),
        (
            "lf-empty-pause-01",
            1,
            2,
            "prose_meaning",
            "你已经完成这一步。",
            False,
        ),
        (
            "choose-scenario-then-navigate",
            1,
            2,
            "prose_meaning",
            "你选了朝东的窗台，请到那里准备记录。你会记下哪两个时间来算窗台的直射光照时长？",
            False,
        ),
        (
            "choose-scenario-then-navigate",
            0,
            1,
            "prose_question",
            "观察地点决定了你要记什么：不同位置，光照的变化方式不一样，需要记录的数据也不同。"
            "先选一个你能实际走到、能连续观察一会儿的地方。",
            True,
        ),
        (
            "clarify-before-answering",
            1,
            2,
            "prose_question",
            "日期统一写成 YYYY-MM-DD 的格式。请用同一个输入回答原题。",
            True,
        ),
        (
            "clarify-before-answering",
            1,
            2,
            "prose_meaning",
            "统一用 YYYY-MM-DD。就是把二〇二六年九月十五日写成规定格式。请继续回答原题。",
            False,
        ),
        (
            "lf-feedback-missing-branch",
            2,
            2,
            "prose_meaning",
            "Try again. Why is the middle of a folded sheet harder to bend?",
            False,
        ),
        (
            "lf-feedback-missing-branch",
            2,
            2,
            "prose_question",
            "The material stays the same — it's the same sheet, same paper, same thickness. "
            "What changes is the shape.\n\nLook again at the unfolded sheet and the folded one: "
            "how does the shape of the sheet across the fold differ from the flat sheet?",
            False,
        ),
    ],
)
def test_live_evaluation_reports_the_reviewed_prose_with_its_evidence(
    case_id: str,
    response_index: int,
    stage: int,
    criterion: str,
    prose: str,
    verdict: bool,
) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    fixture = next(case for case in catalog if case["id"] == case_id)
    fixture["replay"][response_index]["text"] = prose
    case = Case.model_validate(fixture)
    requests = []
    intent_key = (
        "required_meaning" if criterion == "prose_meaning" else "intended_question"
    )

    def assessment(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = next(
            part for part in messages[-1].parts if isinstance(part, UserPromptPart)
        )
        evidence = json.loads(prompt.content)
        requests.append(evidence)
        key = "covered" if "required_meaning" in evidence else "asked"
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        key: (
                            verdict
                            if intent_key in evidence and evidence["prose"] == prose
                            else True
                        ),
                        "reason": "Recorded human decision",
                    },
                )
            ]
        )

    result = asyncio.run(
        evaluate_case(
            case, Replay(case.replay).model, judge_model=FunctionModel(assessment)
        )
    )

    expected = fixture["steps"][stage - 1]["expected"]
    evidence = {intent_key: expected[criterion], "prose": prose}
    if criterion == "prose_question":
        evidence["previous_question"] = (
            fixture["steps"][stage - 2]["expected"]["question"]["question"]
            if stage > 1
            else None
        )
        if stage > 1:
            previous_prose = fixture["replay"][0]["text"]
            evidence["previous_prose"] = previous_prose
            assert (
                result["steps"][stage - 1]["question_judgment"]["previous_prose"]
                == previous_prose
            )
    assert [
        request
        for request in requests
        if intent_key in request and request["prose"] == prose
    ] == [evidence]
    assert result["steps"][stage - 1]["criteria"][criterion] == (
        "passed" if verdict else "failed"
    )
    assert result["failures"] == ([] if verdict else [f"step_{stage}.{criterion}"])
    assert result["steps"][-1]["outcome"] == "finished"


def test_previous_question_requires_the_same_single_visible_control() -> None:
    previous = {"questions": [{"title": QUESTION, "controls": "?[...Your answer]"}]}
    assert repeated_visible_question(previous, previous) == QUESTION
    assert repeated_visible_question(None, previous) is None
    assert (
        repeated_visible_question(
            previous,
            {"questions": [{"title": QUESTION, "controls": "?[...Different input]"}]},
        )
        is None
    )
    assert (
        repeated_visible_question(
            previous,
            {"questions": [{"title": "Which tool?", "controls": "?[...Your answer]"}]},
        )
        is None
    )
    assert (
        repeated_visible_question(previous, {"questions": previous["questions"] * 2})
        is None
    )


@pytest.mark.parametrize(
    ("expected_type", "button", "binding", "failures", "executed_steps"),
    [
        ("single", "继续", "", [], 2),
        (
            "single",
            "继续",
            "继续",
            ["step_1.question.question", "step_1.question.variable"],
            2,
        ),
        ("multi", "继续", "", ["step_1.question.type"], 2),
        (
            "multi",
            "跳过",
            "",
            ["step_1.question.type", "step_1.question.options"],
            1,
        ),
    ],
    ids=[
        "unbound-single",
        "unexpected-answer-binding",
        "planned-button-present",
        "planned-button-absent",
    ],
)
def test_live_evaluator_checks_authored_navigation_and_clicks_the_available_button(
    expected_type: str,
    button: str,
    binding: str,
    failures: list[str],
    executed_steps: int,
) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    fixture = next(case for case in catalog if case["id"] == "lf-empty-pause-01")
    for step in fixture["steps"]:
        step["expected"].pop("prose_meaning", None)
    fixture["steps"][0]["expected"]["question"]["type"] = expected_type
    fixture["replay"][0]["calls"][0]["args"] = {
        "type": "single",
        "options": [{"display": button, "value": button}],
    }
    if binding:
        fixture["replay"][0]["calls"][0]["args"]["question"] = binding
    case = Case.model_validate(fixture)

    result = asyncio.run(evaluate_case(case, Replay(case.replay).model))

    assert result["status"] == (
        "behavior_failure" if failures else "first_attempt_pass"
    )
    assert result["failures"] == failures
    assert result["steps"][0]["question"]["options"] == [[button, button]]
    assert "核对小袋" not in result["steps"][0]["prose"]
    assert len(result["steps"]) == executed_steps
    if executed_steps == 2:
        assert result["steps"][1]["action"] == "answer"
        assert result["steps"][1]["outcome"] == "finished"
        assert result["steps"][1]["memory"] == {}
        assert result["steps"][1]["memory_updates"] == []
        assert "核对小袋" in result["steps"][1]["prose"]


@pytest.mark.parametrize("title", ["", "开始记录", "选一个观察项目"])
@pytest.mark.parametrize(
    "case_id", ["choose-scenario-then-navigate", "choose-balcony-then-navigate"]
)
def test_start_recording_accepts_any_question(title: str, case_id: str) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    fixture = next(entry for entry in catalog if entry["id"] == case_id)
    fixture["replay"][1]["calls"][0]["args"]["question"] = title
    case = Case.model_validate(fixture)

    result = asyncio.run(evaluate_case(case))

    navigation = result["steps"][1]
    assert navigation["question"]["question"] == title
    assert navigation["question"]["variable"] == (title or None)
    assert navigation["criteria"]["question.options"] == "passed"
    assert result["status"] == "first_attempt_pass"
    after_click = result["steps"][2]
    assert after_click["criteria"]["question.question"] == "passed"
    assert after_click["memory"] == navigation["memory"]
    assert after_click["memory_updates"] == []


def test_balcony_replay_rejects_the_windowsill_branch_after_reload() -> None:
    catalog = {
        row["id"]: row for row in json.loads(CATALOG.read_text(encoding="utf-8"))
    }
    balcony = catalog["choose-balcony-then-navigate"]
    windowsill = catalog["choose-scenario-then-navigate"]
    assert balcony["teaching_prompt"] == windowsill["teaching_prompt"]
    balcony["replay"][2] = windowsill["replay"][2]

    result = asyncio.run(evaluate_case(Case.model_validate(balcony)))

    assert result["status"] == "behavior_failure"
    after_click = result["steps"][2]
    assert after_click["reloaded"] is True
    assert after_click["criteria"]["memory"] == "passed"
    assert after_click["criteria"]["question.question"] == "failed"


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
    report = _report(output)
    (result,) = report["results"]
    assert result["status"] == "behavior_failure"
    assert failure in result["failures"]
    stage, criterion = failure.split(".", 1)
    assert (
        result["steps"][int(stage.removeprefix("step_")) - 1]["criteria"][criterion]
        == "failed"
    )
    assert report["criteria_summary"][criterion]["failed"] >= 1
    if problem == "premature_finish":
        assert result["steps"][0]["criteria"]["question.type"] == "not_evaluated"
        assert report["criteria_summary"]["memory"]["not_evaluated"] == 2
        assert [step["stage"] for step in result["unreached_steps"]] == [2, 3]


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


@pytest.mark.parametrize("live", [False, True])
def test_model_failure_preserves_the_observed_memory_check(live: bool) -> None:
    fixture = _case()
    fixture["steps"][-1]["expected"]["memory"] = {QUESTION: "park"}
    fixture["replay"].pop()
    case = Case.model_validate(fixture)
    model = Replay(case.replay).model if live else None

    result = asyncio.run(evaluate_case(case, model))

    assert result["status"] == ("call_failure" if live else "behavior_failure")
    assert result["failures"] == ["step_3.memory", "ReplayExhaustedError"]
    final = result["steps"][-1]
    assert final["memory"] == {QUESTION: "garden"}
    assert final["criteria"]["memory"] == "failed"
    assert final["criteria"]["prose_contains[0]"] == "not_evaluated"


def test_model_call_records_partial_response_when_stream_fails() -> None:
    error = OSError("provider connection interrupted")

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Partial lesson."
        yield {0: DeltaToolCall(name="finish", json_args="{", tool_call_id="finish-1")}
        raise error

    model = ObservedModel(FunctionModel(stream_function=stream), record_calls=True)

    async def receive() -> None:
        async with model.request_stream([], None, ModelRequestParameters()) as response:
            async for _ in response:
                pass

    with pytest.raises(OSError, match="provider connection interrupted") as caught:
        asyncio.run(receive())

    assert caught.value is error
    assert model.model_calls == [
        {
            "number": 1,
            "parts": [
                {"text": "Partial lesson."},
                {"tool": "finish", "arguments": "{"},
            ],
            "error": "OSError",
        }
    ]


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
    (turn,) = result["steps"][0]["turns"]
    assert control in turn["engine_prose"]
    assert control not in turn["prose"]


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
    assert result["run_id"] != prior["run_id"]
    assert result["prompt_sha256"] != prior["prompt_sha256"]
    assert result["comparison"]["compatible"]
    assert result["comparison"]["prompt_changed"]

    process = _run(*args, "--case", "park-choice", *comparison)
    assert process.returncode == 2, process.stdout + process.stderr
    result = _report(candidate)
    assert result["comparison"]["compatible"] is False
    assert result["comparison"]["mismatches"]


@pytest.mark.parametrize("suite", ["smoke", "all"])
def test_bundled_suite_replays_every_selected_case(tmp_path: Path, suite: str) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    selected = [case for case in catalog if suite == "all" or case.get("smoke")]
    expected_meaning_checks = sum(
        "prose_meaning" in step.get("replay_expected", step["expected"])
        for case in selected
        for step in case["steps"]
    )
    output = tmp_path / "replay.json"
    process = _run("--suite", suite, "--json", str(output))
    assert process.returncode == 0, process.stdout + process.stderr
    report = _report(output)
    assert report["review_items"] == []
    assert report["criteria_summary"]["prose_question"]["not_evaluated"] > 0
    assert (
        report["criteria_summary"]["prose_meaning"]["not_evaluated"]
        == expected_meaning_checks
    )
    results = report["results"]
    assert [result["case_id"] for result in results] == [
        case["id"] for case in selected
    ]
    reproduced = {
        result["case_id"]
        for result in results
        if result["status"] == "expected_failure_replayed"
    }
    expected_failures = (
        {"synthetic-narrated-fallback", "synthetic-retry-exhaustion"}
        if suite == "all"
        else set()
    )
    assert reproduced == expected_failures
    if suite == "all":
        exhausted = next(
            row for row in results if row["case_id"] == "synthetic-retry-exhaustion"
        )
        step = exhausted["steps"][0]
        assert len(step["model_calls"]) == 4
        first, retry, *_ = step["model_calls"]
        tool = next(part for part in first["parts"] if part.get("tool") == "interact")
        assert json.loads(tool["arguments"])["variable"] == "garden"
        assert retry["retry_feedback"][0]["tool"] == "interact"
        assert "variable" in retry["retry_feedback"][0]["message"]


@pytest.mark.parametrize("target", ["baseline", "output", "review_input"])
def test_report_writers_reject_hard_link_aliases(tmp_path: Path, target: str) -> None:
    cases = tmp_path / "cases.json"
    output = tmp_path / "results.json"
    page = output.with_suffix(".review.html")
    original = output if target == "output" else tmp_path / "original.json"
    _write_cases(cases, _case())
    original.write_bytes(b'{"saved":true}')
    page.hardlink_to(original)
    if target == "review_input":
        cli = review_main
        args = ["--output", str(page), str(original)]
    else:
        cli = main
        args = ["--cases", str(cases), "--json", str(output)]
        if target == "baseline":
            args.extend(["--compare", str(original)])

    with pytest.raises(SystemExit, match="2"):
        cli(args)

    assert original.read_bytes() == b'{"saved":true}'


@pytest.mark.parametrize("field", ["run_id", "unreached_steps", "questions"])
def test_review_rejects_data_the_browser_cannot_render(
    tmp_path: Path, field: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = tmp_path / "cases.json"
    report_path = tmp_path / "results.json"
    page = tmp_path / "review.html"
    _write_cases(cases, _case())
    assert main(["--cases", str(cases), "--json", str(report_path)]) == 0
    report = _report(report_path)
    row = report["results"][0]
    target = {"run_id": report, "unreached_steps": row, "questions": row["steps"][0]}
    target[field][field] = 42
    report_path.write_text(json.dumps(report), encoding="utf-8")
    page.write_text("Saved page", encoding="utf-8")

    assert review_main(["--output", str(page), str(report_path)]) == 2

    assert field in capsys.readouterr().err
    assert page.read_text(encoding="utf-8") == "Saved page"


def test_review_reopens_legacy_reports_with_matching_fixtures(tmp_path: Path) -> None:
    cases = tmp_path / "cases.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    comparison = tmp_path / "review.html"
    case = _case()
    _write_cases(cases, case)
    process = _run("--cases", str(cases), "--json", str(first))
    assert process.returncode == 0, process.stdout + process.stderr
    legacy = _report(first)
    del legacy["review_context"], legacy["run_id"]
    prose = "<div>Slide text<script>window.untrusted = true</script></div>\n\n![image](https://example.org/image)"
    legacy["results"][0]["steps"][0]["prose"] = prose
    first.write_text(json.dumps(legacy), encoding="utf-8")
    second.write_text(
        json.dumps({**legacy, "model": "another model"}), encoding="utf-8"
    )
    args = ["--output", str(comparison), "--cases", str(cases), str(first), str(second)]

    assert review_main(args) == 0
    page = comparison.read_text(encoding="utf-8")
    payload = _review_payload(page)
    left, right = payload["runs"]
    assert left["id"] != right["id"]
    assert page.count("</script>") == 2
    step = left["results"][0]["steps"][0]
    assert step["prose"] == prose
    assert "<li>Slide text</li>" in step["rendered_prose"]
    assert "<script" not in step["rendered_prose"]
    assert "<img" not in step["rendered_prose"]
    assert (
        payload["context"]["garden-choice"]["teaching_prompt"]
        == case["teaching_prompt"]
    )

    _write_cases(cases, {**case, "teaching_prompt": "Changed lesson"})
    assert review_main(args) == 2
    assert comparison.read_text(encoding="utf-8") == page


def test_legacy_review_recovers_when_the_default_catalog_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import evaluate_mdf_interactions as evaluator

    cases = tmp_path / "cases.json"
    output = tmp_path / "result.json"
    _write_cases(cases, _case())
    assert main(["--cases", str(cases), "--json", str(output)]) == 0
    report = _report(output)
    del report["review_context"], report["run_id"]
    output.write_text(json.dumps(report), encoding="utf-8")
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(evaluator, "CASES_PATH", missing)
    page = tmp_path / "legacy-review.html"
    args = ["--output", str(page), str(output)]

    assert review_main(args) == 0
    saved = page.read_text(encoding="utf-8")
    data = _review_payload(saved)
    assert data["context"] == {}
    assert data["runs"][0]["results"][0]["steps"][0]["prose"] == QUESTION

    assert review_main([*args, "--cases", str(missing)]) == 2
    assert page.read_text(encoding="utf-8") == saved


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


def test_bundled_catalog_retains_distinct_trace_anomalies() -> None:
    cases = json.loads(CATALOG.read_text(encoding="utf-8"))
    cases_by_id = {case["id"]: case for case in cases}
    required_replays = {
        "lf-empty-pause-01": "empty-pause",
        "lf-retired-prompt-02": "retired-prompt",
        "lf-missing-stem-03": "missing-stem",
        "lf-wrong-binding-05": "wrong-binding",
        "lf-extra-pause-06": "extra-pause",
        "lf-feedback-wrong-answer-id": "wrong_answer_id",
        "lf-feedback-control-only-retry": "control_only_retry",
        "lf-feedback-missing-branch": "missing_feedback",
        "lf-feedback-checking-placeholder": "invalid_direction_placeholder",
    }
    for case_id, anomaly in required_replays.items():
        case = cases_by_id[case_id]
        assert case["source"] == "langfuse", case_id
        assert {"observed-anomaly", anomaly} <= set(case["tags"]), case_id


def test_bundled_smoke_suite_covers_choice_text_and_combined_submissions() -> None:
    cases = json.loads(CATALOG.read_text(encoding="utf-8"))
    smoke = [case for case in cases if case.get("smoke")]
    assert all(not case.get("replay_only") for case in smoke)
    submissions = {
        (
            previous["expected"]["question"]["type"],
            bool(step.get("values")),
            bool(step.get("text")),
        )
        for case in smoke
        for previous, step in zip(case["steps"], case["steps"][1:], strict=False)
        if step["action"] == "answer" and previous["expected"].get("question")
    }
    assert {
        ("single", True, False),
        ("multi", True, False),
        ("text", False, True),
        ("single_or_text", True, False),
        ("single_or_text", False, True),
        ("multi_or_text", True, False),
        ("multi_or_text", False, True),
        ("multi_or_text", True, True),
    } <= submissions


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
