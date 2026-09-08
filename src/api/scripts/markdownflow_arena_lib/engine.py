"""Generate isolated MarkdownFlow comparison artifacts through shared runtime layers."""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from .source import case_input_hash
from .state import ArenaError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


def _model_catalog(app: Flask) -> list[dict]:
    from flaskr.api.llm import get_current_models

    return get_current_models(app)


def resolve_models(app: Flask, requested: list[str]) -> list[dict]:
    """Resolve exact IDs or unique exact unprefixed IDs, without changing model versions."""
    catalog = _model_catalog(app)
    resolved = []
    seen = set()
    for requested_model in requested:
        name = requested_model.strip()
        matches = [item for item in catalog if item["model"] == name]
        if not matches and name and "/" not in name:
            matches = [
                item for item in catalog if item["model"].rsplit("/", 1)[-1] == name
            ]
        if len(matches) != 1:
            message = f"Model {name!r} is unavailable or ambiguous in the configured model catalog"
            raise ArenaError(message)
        match = matches[0]
        if match["model"] in seen:
            message = "Comparison models must resolve to distinct model IDs"
            raise ArenaError(message)
        seen.add(match["model"])
        resolved.append(
            {
                "requested": name,
                "model": match["model"],
                "display_name": match.get("display_name") or match["model"],
            }
        )
    if not resolved:
        message = "At least one model is required"
        raise ArenaError(message)
    return resolved


def _chat_llm(*args: object, **kwargs: object) -> Iterator:
    from flaskr.api.llm import chat_llm

    return chat_llm(*args, **kwargs)


class _ArenaProvider:
    """Keep fixed-model requests, exact input hashes, and terminal metadata per run."""

    def __init__(
        self,
        app: Flask,
        case: dict,
        model: dict,
        span: object,
        usage_context: object,
        usage_scene: int,
    ) -> None:
        self.app = app
        self.case = case
        self.model = model["model"]
        self.span = span
        self.usage_context = usage_context
        self.usage_scene = usage_scene
        self.requests: list[dict] = []
        self.outputs: list[str] = []

    def _run(self, messages: list[dict[str, str]], *, stream: bool) -> Iterator[str]:
        frozen_messages = copy.deepcopy(messages)
        request_metadata = {
            "messages_hash": hashlib.sha256(
                json.dumps(
                    frozen_messages,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        }
        self.requests.append(request_metadata)
        for response in _chat_llm(
            self.app,
            self.case["owner_user_bid"],
            self.span,
            model=self.model,
            messages=frozen_messages,
            stream=stream,
            temperature=float(self.case.get("temperature", 0.3)),
            generation_name="markdownflow_arena",
            usage_context=self.usage_context,
            usage_scene=self.usage_scene,
            completion_observer=request_metadata.update,
        ):
            if response.result:
                self.outputs.append(response.result)
                yield response.result

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Use the frozen comparison model even when a library passes overrides."""
        del model, temperature
        return "".join(self._run(messages, stream=False))

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Iterator[str]:
        """Use the same frozen configuration for every streamed request."""
        del model, temperature
        yield from self._run(messages, stream=True)


def _runtime() -> dict:
    from flaskr.api.langfuse import (
        create_trace_with_root_span,
        finalize_langfuse_trace,
        get_langfuse_client,
    )
    from flaskr.i18n import get_current_language, set_language
    from flaskr.service.learn.context_v2 import (
        MdflowContextV2,
        RunScriptPreviewContextV2,
    )
    from flaskr.service.learn.learner_profile_prompt import (
        build_course_prompt,
        render_course_prompt_identity_variables,
    )
    from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
    from flaskr.service.metering import UsageContext
    from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
    from markdown_flow import ProcessMode

    return {
        "create_trace": create_trace_with_root_span,
        "finalize_trace": finalize_langfuse_trace,
        "langfuse_client": get_langfuse_client,
        "get_language": get_current_language,
        "set_language": set_language,
        "context": MdflowContextV2,
        "preview": RunScriptPreviewContextV2,
        "adapter": PreviewElementRunAdapter,
        "usage_context": UsageContext,
        "usage_scene": BILL_USAGE_SCENE_PREVIEW,
        "mode": ProcessMode.STREAM,
        "compose_prompt": build_course_prompt,
        "render_identity": render_course_prompt_identity_variables,
    }


def _versions() -> dict[str, str]:
    versions = {}
    for package in ("markdown-flow", "litellm"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "unavailable"
    return versions


def _completion_status(requests: list[dict]) -> str:
    if not requests:
        return "generation_failed"
    if any(
        item.get("partial_response")
        or item.get("finish_reason") in {"length", "max_tokens"}
        for item in requests
    ):
        return "truncated"
    if any(item.get("finish_reason") not in {"stop", "end_turn"} for item in requests):
        return "generation_failed"
    return "complete"


def generate_case(app: Flask, case: dict, model: dict) -> dict:
    """Run a frozen case with no preview cache, learner profile reads, or progress writes."""
    if case_input_hash(case) != case.get("input_hash"):
        message = "Frozen case input hash does not match its content"
        raise ArenaError(message)
    if not case.get("owner_user_bid"):
        message = "A frozen owner user ID is required"
        raise ArenaError(message)
    runtime = _runtime()
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    metadata = {"run_id": run_id, "model": model["model"], "versions": _versions()}
    output = {
        "status": "generation_failed",
        "content": "",
        "elements": [],
        "metadata": metadata,
        "input_hash": case["input_hash"],
    }
    provider = None
    trace = span = None
    with app.app_context():
        original_language = runtime["get_language"]()
        try:
            runtime["set_language"](case["output_language"])
            trace, span = runtime["create_trace"](
                client=runtime["langfuse_client"](),
                trace_payload={
                    "id": run_id,
                    "name": "markdownflow_arena",
                    "user_id": case["owner_user_bid"],
                    "metadata": {
                        "case_id": case["case_id"],
                        "input_hash": case["input_hash"],
                    },
                },
                root_span_payload={"name": "markdownflow_arena"},
            )
            usage = runtime["usage_context"](
                user_bid=case["owner_user_bid"],
                shifu_bid=case["source"]["shifu_bid"],
                outline_item_bid=case["source"]["outline_bid"],
                usage_scene=runtime["usage_scene"],
            )
            provider = _ArenaProvider(
                app, case, model, span, usage, runtime["usage_scene"]
            )
            variables = copy.deepcopy(case["variables"])
            prompt = runtime["compose_prompt"](
                case["document_prompt"],
                variables=variables,
                nickname_identifiers=(case["owner_user_bid"],),
            )
            prompt = runtime["render_identity"](prompt, variables)
            context = runtime["context"](
                document=case["document"],
                document_prompt=prompt,
                llm_provider=provider,
                interaction_prompt=case.get("interaction_prompt"),
                interaction_error_prompt=case.get("interaction_error_prompt"),
                use_learner_language=case["use_learner_language"],
                output_language=case["output_language"],
            )
            result = context.process(
                block_index=case["block_index"],
                mode=runtime["mode"],
                context=copy.deepcopy(case["context"]),
                variables=variables,
                user_input=copy.deepcopy(case["user_input"]),
            )
            adapter = runtime["adapter"](
                app,
                shifu_bid=case["source"]["shifu_bid"],
                outline_bid=case["source"]["outline_bid"],
                user_bid=case["owner_user_bid"],
                run_session_bid=run_id,
            )
            preview = runtime["preview"](app)
            events = preview._iter_preview_generated_events(
                result=result,
                outline_bid=case["source"]["outline_bid"],
                block_index=case["block_index"],
                current_block=context.get_block(case["block_index"]),
                is_user_input_validation=bool(case["user_input"]),
                content_chunks=[],
                langfuse_output_chunks=[],
            )
            for _event in adapter.process(events):
                pass
            output["elements"] = [
                element.model_dump(mode="json")
                for element in sorted(
                    adapter._latest_element_snapshots.values(),
                    key=lambda item: (item.element_index, item.sequence_number),
                )
            ]
            output["status"] = _completion_status(provider.requests)
            if not output["elements"]:
                output["status"] = "generation_failed"
                metadata["error_class"] = "EmptyRenderedOutput"
        except Exception as exc:
            output["status"] = "generation_failed"
            metadata["error_class"] = type(exc).__name__
        finally:
            if provider is not None:
                output["content"] = "".join(provider.outputs)
                metadata["requests"] = provider.requests
            metadata["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            try:
                if trace is not None:
                    runtime["finalize_trace"](
                        trace=trace,
                        root_span=span,
                        trace_payload={"output": output["content"]},
                        root_span_payload={"output": output["content"]},
                    )
            except Exception:
                metadata["tracing_failure"] = True
            finally:
                runtime["set_language"](original_language)
    return output
