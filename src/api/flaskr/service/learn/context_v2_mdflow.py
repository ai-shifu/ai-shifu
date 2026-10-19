"""MarkdownFlow and LLM collaborators shared by the learning runtime."""

from collections.abc import Generator, Iterable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from flask import Flask
from flaskr.api.langfuse import (
    LangfuseTraceHandle,
)
from flaskr.api.llm import chat_llm
from flaskr.common.i18n_utils import (
    get_markdownflow_output_language,
    resolve_markdownflow_output_language,
)
from flaskr.i18n import get_current_language
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_generation_name,
)
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnProgressRecord,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
)
from flaskr.service.profile.constants import SYS_USER_LANGUAGE
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from markdown_flow import (
    USER_ANSWER_CONTEXT_KEY,
    InteractionParser,
    LLMProvider,
    MarkdownFlow,
    ProcessMode,
    replace_variables_in_text,
)
from markdown_flow.llm import LLMResult
from markdown_flow.models import Block


def _normalize_stream_number(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _iter_llm_result_content_parts(
    llm_result: object,
) -> Generator[tuple[str, str, int | None], None, None]:
    if llm_result is None:
        return

    formatted_elements = getattr(llm_result, "formatted_elements", None)
    if isinstance(formatted_elements, list) and formatted_elements:
        emitted_formatted = False
        for item in formatted_elements:
            item_content = getattr(item, "content", None)
            if item_content is None and isinstance(item, dict):
                item_content = item.get("content")
            item_content = str(item_content or "")
            if not item_content:
                continue

            stream_type = getattr(item, "type", None)
            if stream_type is None and isinstance(item, dict):
                stream_type = item.get("type")
            stream_number = getattr(item, "number", None)
            if stream_number is None and isinstance(item, dict):
                stream_number = item.get("number")

            emitted_formatted = True
            yield (
                item_content,
                str(stream_type or ""),
                _normalize_stream_number(stream_number),
            )

        if emitted_formatted:
            return

    if hasattr(llm_result, "content"):
        content = str(getattr(llm_result, "content", "") or "")
    else:
        content = str(llm_result or "")
    if not content:
        return

    yield (
        content,
        str(getattr(llm_result, "type", "") or ""),
        _normalize_stream_number(getattr(llm_result, "number", None)),
    )


class RunType(Enum):
    """Enumerate supported run type values."""

    INPUT = "input"
    OUTPUT = "output"


class RunScriptInfo:
    """Carry script identity and metadata for a learning run."""

    attend: LearnProgressRecord
    outline_bid: str
    block_position: int
    mdflow: str

    def __init__(
        self,
        attend: LearnProgressRecord,
        outline_bid: str,
        block_position: int,
        mdflow: str,
    ) -> None:
        """Capture the current run-script position and MarkdownFlow source."""
        self.attend = attend
        self.outline_bid = outline_bid
        self.block_position = block_position
        self.mdflow = mdflow


def _resolve_runtime_output_language(user_profile: dict | None) -> str:
    runtime_language = get_current_language()
    profile = user_profile or {}
    profile_language = profile.get(SYS_USER_LANGUAGE) or profile.get("language") or ""
    return str(runtime_language or profile_language or "")


def _resolve_runtime_language_context(
    user_profile: dict | None,
    *,
    use_learner_language: bool,
) -> tuple[dict, str]:
    """Keep runtime prompt variables aligned with the per-request language."""
    resolved_profile = dict(user_profile or {})
    output_language = _resolve_runtime_output_language(resolved_profile)
    if use_learner_language and output_language:
        resolved_profile[SYS_USER_LANGUAGE] = output_language
        resolved_profile["language"] = output_language
    return resolved_profile, output_language


class RUNLLMProvider(LLMProvider):
    """Provide model calls for the learning runtime."""

    app: Flask
    llm_settings: LLMSettings
    trace: LangfuseTraceHandle
    parent_observation: Any
    trace_args: dict
    usage_context: UsageContext
    usage_scene: int

    def __init__(
        self,
        app: Flask,
        llm_settings: LLMSettings,
        trace: LangfuseTraceHandle,
        parent_observation: object,
        trace_args: dict,
        usage_context: UsageContext,
        usage_scene: int,
    ) -> None:
        """Bind run-scoped LLM settings, tracing, and usage dependencies."""
        self.app = app
        self.llm_settings = llm_settings
        self.trace = trace
        self.parent_observation = parent_observation
        self.trace_args = trace_args
        self.usage_context = usage_context
        self.usage_scene = usage_scene

    def set_usage_generated_block_bid(self, generated_block_bid: str) -> None:
        """Attach the generated block to LLM usage tracking."""
        self.usage_context = replace(
            self.usage_context,
            generated_block_bid=str(generated_block_bid or ""),
        )

    def _log_preview_output(
        self,
        *,
        model: str,
        temperature: float | None,
        output: str,
    ) -> None:
        if self.usage_scene != BILL_USAGE_SCENE_PREVIEW:
            return

        metadata = self.trace_args.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        self.app.logger.info(
            "preview llm output | shifu_bid=%s | outline_bid=%s | session_id=%s | scene=%s | model=%s | temperature=%s | output=%s",
            metadata.get("shifu_bid", ""),
            metadata.get("outline_bid", ""),
            metadata.get("session_id", ""),
            metadata.get("scene", ""),
            model,
            temperature,
            output,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        # Extract the last message content as the main prompt
        """Start a nonstreaming LLM completion and return its text."""
        if not messages:
            message = "No messages provided"
            raise ValueError(message)
        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )
        metadata = self.trace_args.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chapter_title = metadata.get("chapter_title", "")
        scene = metadata.get("scene", "lesson_runtime")
        generation_name = build_langfuse_generation_name(
            chapter_title,
            scene,
            "run_llm",
        )

        res = chat_llm(
            self.app,
            self.trace_args.get("user_id", ""),
            self.parent_observation,
            messages=messages,
            model=actual_model,
            stream=False,
            generation_name=generation_name,
            temperature=actual_temperature,
            usage_context=self.usage_context,
            usage_scene=self.usage_scene,
            usage_metadata=self.llm_settings.usage_metadata,
        )
        # Collect all stream responses and concatenate the results
        content_parts = [response.result for response in res if response.result]
        output = "".join(content_parts)
        self._log_preview_output(
            model=actual_model,
            temperature=actual_temperature,
            output=output,
        )
        return output

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, None]:
        # Extract the last message content as the main prompt
        """Start a streaming LLM completion and yield its response chunks."""
        if not messages:
            message = "No messages provided"
            raise ValueError(message)

        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )
        metadata = self.trace_args.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chapter_title = metadata.get("chapter_title", "")
        scene = metadata.get("scene", "lesson_runtime")
        generation_name = build_langfuse_generation_name(
            chapter_title,
            scene,
            "run_llm",
        )

        # Check if there's a system message
        self.app.logger.info("stream invoke_llm begin")
        res = chat_llm(
            self.app,
            self.trace_args["user_id"],
            self.parent_observation,
            model=actual_model,
            messages=messages,
            stream=True,
            generation_name=generation_name,
            temperature=actual_temperature,
            usage_context=self.usage_context,
            usage_scene=self.usage_scene,
            usage_metadata=self.llm_settings.usage_metadata,
        )
        self.app.logger.info("stream invoke_llm res: %s", res)
        first_result = False
        for i in res:
            if i.result:
                if not first_result:
                    first_result = True
                    self.app.logger.info("stream first result: %s", i.result)
                yield i.result
        self.app.logger.info("stream invoke_llm end")


class MdflowContextV2:
    """Track shared MarkdownFlow state for a version-two learning run."""

    def __init__(
        self,
        *,
        document: str,
        document_prompt: str | None = None,
        llm_provider: LLMProvider | None = None,
        interaction_prompt: str | None = None,
        interaction_error_prompt: str | None = None,
        use_learner_language: bool = False,
        visual_mode: bool = True,
        output_language: str | None = None,
    ) -> None:
        """Create MarkdownFlow with prompts and optional output-language handling.

        Initializes MarkdownFlow with the document, provider, and configured prompts.
        When learner-language output is enabled, resolves and applies the requested
        or fallback language.
        """
        self._mdflow = MarkdownFlow(
            document=document,
            llm_provider=llm_provider,
            document_prompt=document_prompt,
            interaction_prompt=interaction_prompt,
            interaction_error_prompt=interaction_error_prompt,
        )
        # markdown_flow>=0.2.44 removed set_visual_mode; keep backward compatibility.
        set_visual_mode = getattr(self._mdflow, "set_visual_mode", None)
        if callable(set_visual_mode):
            set_visual_mode(visual_mode)
        # Language must follow the learner profile/preview variables when provided;
        # falling back to the request-local language keeps existing callers compatible.
        if use_learner_language:
            language = (output_language or "").strip()
            resolved_output_language = (
                resolve_markdownflow_output_language(language)
                if language
                else get_markdownflow_output_language()
            )
            self._mdflow = self._mdflow.set_output_language(resolved_output_language)

    def get_block(self, block_index: int) -> Block:
        """Return a MarkdownFlow block by its index."""
        return self._mdflow.get_block(block_index)

    def get_all_blocks(self) -> list[Block]:
        """Return all MarkdownFlow blocks in encounter order."""
        return self._mdflow.get_all_blocks()

    def process(
        self,
        *,
        block_index: int,
        mode: ProcessMode,
        context: list[dict[str, str]] | None = None,
        variables: dict | None = None,
        user_input: dict[str, list[str]] | None = None,
    ) -> LLMResult | Generator[LLMResult, None, None]:
        """Process the current MarkdownFlow content."""
        return self._mdflow.process(
            block_index=block_index,
            mode=mode,
            context=context,
            variables=variables,
            user_input=user_input,
        )

    @staticmethod
    def normalize_context_messages(
        context: Iterable[dict[str, str]] | None,
    ) -> list[dict[str, str]] | None:
        """Normalize messages for the model context."""
        if not context:
            return None
        filtered: list[dict[str, str]] = []
        for msg in context:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content", "")
            if not role or not content or not str(content).strip():
                continue
            filtered.append({"role": role, "content": str(content)})
        return filtered or None

    @staticmethod
    def filter_context_by_output_language(
        context: list[dict[str, str]] | None,
        output_language: str,
    ) -> list[dict[str, str]] | None:
        """Keep context compatible with the output language."""
        if not context:
            return context
        normalized_language = (output_language or "").strip().lower()
        if not normalized_language or normalized_language in {"en", "en-us", "english"}:
            return context

        filtered: list[dict[str, str]] = []
        for message in context:
            content = str(message.get("content") or "")
            if "OUTPUT: 100% English" in content:
                continue
            if "Translate ALL non-English" in content:
                continue
            filtered.append(message)
        return filtered or None

    @staticmethod
    def normalize_user_input_map(
        input_value: str | dict | list | None,
        default_key: str = "input",
    ) -> dict[str, list[str]]:
        """Normalize learner inputs into the context schema."""
        if input_value is None:
            return {}
        if isinstance(input_value, dict):
            normalized = {}
            for key, raw in input_value.items():
                if raw is None:
                    continue
                if isinstance(raw, list):
                    cleaned = [str(item) for item in raw if item is not None]
                else:
                    cleaned = [str(raw)]
                if cleaned:
                    normalized[str(key)] = cleaned
            return normalized
        if isinstance(input_value, list):
            cleaned = [str(item) for item in input_value if item is not None]
            return {default_key: cleaned} if cleaned else {}
        return {default_key: [str(input_value)]}

    @staticmethod
    def flatten_user_input_map(
        user_input: dict[str, list[str]] | None,
    ) -> str:
        """Flatten normalized learner inputs for prompt use."""
        if not user_input:
            return ""
        values: list[str] = []
        for value in user_input.values():
            if isinstance(value, list):
                values.extend([str(item) for item in value if item is not None])
            elif value is not None:
                values.append(str(value))
        return ",".join(values)

    @staticmethod
    def build_context_from_blocks(
        blocks: Iterable["LearnGeneratedBlock"],
        document: str,
        variables: dict | None = None,
    ) -> list[dict[str, str]]:
        """Build model context from MarkdownFlow blocks."""
        message_list: list[dict[str, str]] = []
        mdflow_context = MdflowContextV2(document=document)
        block_list = mdflow_context.get_all_blocks()

        from flask import current_app

        current_app.logger.info("build_context_from_blocks variables: %s", variables)

        for generated_block in blocks:
            if generated_block.position < 0 or generated_block.position >= len(
                block_list
            ):
                continue
            block = block_list[generated_block.position]
            if generated_block.type == BLOCK_TYPE_MDCONTENT_VALUE:
                # Prefer the persisted exact user message sent to the LLM at
                # generation time: replaying it verbatim keeps the rebuilt
                # history byte-identical to previously sent requests so
                # provider-side prefix caching keeps matching. Legacy rows
                # without it fall back to re-rendering the block source with
                # the current variables (one-time cache break, then stable).
                stored_prompt = getattr(generated_block, "generation_prompt", "") or ""
                message_list.append(
                    {
                        "role": "user",
                        "content": stored_prompt
                        or replace_variables_in_text(block.content or "", variables)
                        or "",
                    }
                )
                message_list.append(
                    {
                        "role": "assistant",
                        "content": generated_block.generated_content or "",
                    }
                )
            elif generated_block.type == BLOCK_TYPE_MDINTERACTION_VALUE:
                interaction = InteractionParser().parse(block.content or "")
                if interaction.get("variable"):
                    # Variable interaction (e.g. ?[%{{var}} A | B]): hand the
                    # raw syntax to markdown-flow, whose
                    # _transform_context_messages expands it into
                    # {user: <value>} + {assistant: "ok"} using `variables`.
                    message_list.append(
                        {
                            "role": "assistant",
                            "content": block.content or "",
                        }
                    )
                else:
                    # No-variable interaction (e.g. plain button choice
                    # ?[A | B | C]): hand the raw syntax to markdown-flow with
                    # the learner's answer attached via USER_ANSWER_CONTEXT_KEY.
                    # The library expands it into {user: answer} +
                    # {assistant: "ok"}, or skips the turn when the answer is
                    # empty (never answered).
                    message_list.append(
                        {
                            "role": "assistant",
                            "content": block.content or "",
                            USER_ANSWER_CONTEXT_KEY: (
                                generated_block.generated_content or ""
                            ).strip(),
                        }
                    )
        return message_list


@dataclass
class _RunStepState:
    """Per-step scaffolding threaded through the run_inner phase methods.

    Built once per step by ``RunScriptContextV2._prepare_step_state`` after
    the run-script info resolves; carries the MDF/LLM collaborators and the
    resolved block so each ``_phase_*`` method receives its inputs
    explicitly instead of sharing generator locals (B6 PR3).
    """

    run_script_info: RunScriptInfo
    llm_settings: LLMSettings
    system_prompt: str | None
    usage_context: UsageContext
    llm_provider: RUNLLMProvider
    mdflow_context: MdflowContextV2
    block_list: list
    user_profile: dict
    message_list: list
    variable_definition_key_id_map: dict[str, str]
    block: Any = None
    has_effective_input: bool = False
    memory_generations: dict[str, int] | None = None
