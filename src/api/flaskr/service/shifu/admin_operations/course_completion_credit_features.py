"""Extract authored course features for a calibrated full-course credit estimate.

The two teaching engines have different accounting boundaries. MarkdownFlow 1.0
parses content, interaction, and verbatim blocks before running a lesson; the
2.0 agent receives the whole script in its first user message. Keep those
boundaries here so calibration uses the same features at training and serving.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING

from flaskr.service.learn.api import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from markdown_flow import BlockType, MarkdownFlow
from markdown_flow.parser import extract_preserved_content

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem


_THOUSAND = 1000
_V2_ANCESTOR_LIMIT = 12
_ENGINE_PROMPTS_DIR = Path(__file__).parents[2] / "learn/agent/engine/prompts"
_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,}).*$")
_V1_SYNTAX = re.compile(
    r"(^---[ \t]*$)|(?<!\\)\?\[[^\]\n]*\](?!\()|%?\{\{[^{}\n]+\}\}|^!?===.*$",
    re.MULTILINE,
)
_LATIN_WORD = re.compile(r"[a-zA-Z\u00c0-\u024f]+")
_FRENCH_WORDS = frozenset(
    {
        "avec",
        "ce",
        "cette",
        "dans",
        "des",
        "est",
        "et",
        "les",
        "nous",
        "pas",
        "pour",
        "que",
        "qui",
        "sont",
        "sur",
        "une",
        "vous",
    }
)
_ENGLISH_WORDS = frozenset(
    {
        "and",
        "are",
        "for",
        "from",
        "have",
        "into",
        "not",
        "that",
        "the",
        "their",
        "this",
        "those",
        "through",
        "with",
        "you",
        "your",
    }
)


@dataclass(frozen=True)
class CourseCreditFeatures:
    """Nine course-level model inputs; character measures use thousands."""

    lesson_count: float
    dynamic_chars_k: float
    static_chars_k: float
    system_chars_k: float
    generated_block_count: float
    interaction_count: float
    char_square_k2: float
    chars_system_k2: float
    chars_blocks_k: float

    def as_mapping(self) -> dict[str, float]:
        """Return fields by their versioned coefficient names."""
        return {field.name: getattr(self, field.name) for field in fields(self)}


def _selected_items(
    outline_items: Iterable[object], visible_leaf_outline_bids: Iterable[str]
) -> tuple[list[object], dict[str, object]]:
    item_map: dict[str, object] = {}
    for item in outline_items:
        bid = str(getattr(item, "outline_item_bid", "") or "").strip()
        if not bid:
            continue
        if bid in item_map:
            message = f"duplicate outline item: {bid}"
            raise ValueError(message)
        item_map[bid] = item

    selected_bids = sorted(
        {
            str(bid or "").strip()
            for bid in visible_leaf_outline_bids
            if str(bid or "").strip()
        }
    )
    if not selected_bids:
        message = "course has no visible lessons"
        raise ValueError(message)
    missing = [bid for bid in selected_bids if bid not in item_map]
    if missing:
        message = f"visible lessons are missing from outline: {missing}"
        raise ValueError(message)
    return [item_map[bid] for bid in selected_bids], item_map


def _effective_prompt(
    item: object,
    item_map: dict[str, object],
    course: object,
    *,
    max_ancestors: int | None = None,
) -> str:
    visited: set[str] = set()
    current = item
    ancestor_count = 0
    while current is not None:
        bid = str(getattr(current, "outline_item_bid", "") or "").strip()
        if bid in visited:
            message = f"outline parent cycle at {bid}"
            raise ValueError(message)
        visited.add(bid)
        prompt = str(getattr(current, "llm_system_prompt", "") or "")
        if prompt.strip():
            return prompt
        parent_bid = str(getattr(current, "parent_bid", "") or "").strip()
        if not parent_bid:
            break
        if max_ancestors is not None and ancestor_count >= max_ancestors:
            break
        if parent_bid not in item_map:
            message = f"missing outline ancestor: {parent_bid}"
            raise ValueError(message)
        current = item_map[parent_bid]
        ancestor_count += 1
    prompt = str(getattr(course, "llm_system_prompt", "") or "")
    return prompt if prompt.strip() else ""


def _v1_lesson_sizes(content: str, prompt: str) -> tuple[int, int, int, int, int]:
    # The learner runtime composes this envelope before creating MarkdownFlow.
    # Actual learner values vary by run, so use its empty-profile baseline;
    # calibration still learns variation from completed learner traces.
    composed_prompt = build_course_prompt(prompt or None, variables={})
    composed_prompt = render_course_prompt_identity_variables(composed_prompt, {})
    flow = MarkdownFlow(content, document_prompt=composed_prompt)
    blocks = flow.get_all_blocks()
    dynamic_chars = 0
    static_chars = 0
    generated_blocks = 0
    interactions = 0
    first_content_index: int | None = None

    for block in blocks:
        if block.block_type == BlockType.CONTENT:
            # The parser substitutes fenced code with placeholders while it
            # finds blocks. Restore it before counting authored model input.
            dynamic_chars += len(
                flow._preprocessor.restore_code_blocks_only(block.content)
            )
            generated_blocks += 1
            if first_content_index is None:
                first_content_index = block.index
        elif block.block_type == BlockType.PRESERVED_CONTENT:
            static_chars += len(
                flow._preprocessor.restore_code_blocks(
                    extract_preserved_content(block.content)
                )
            )
        elif block.block_type == BlockType.INTERACTION:
            interactions += 1
        else:
            message = f"unsupported MarkdownFlow block type: {block.block_type}"
            raise ValueError(message)

    system_chars = 0
    if first_content_index is not None:
        # This is the system message the 1.0 engine sends for a content block,
        # including its default framework prompt and inherited author prompt.
        messages = flow.get_content_messages(first_content_index, variables={})
        system_chars = sum(
            len(message["content"])
            for message in messages
            if message.get("role") == "system"
        )
    return dynamic_chars, static_chars, system_chars, generated_blocks, interactions


def _outside_fenced_code(content: str) -> str:
    """Use the agent's 1.0-syntax fence convention for code examples."""
    out: list[str] = []
    opening: str | None = None
    for line in content.splitlines():
        match = _FENCE_OPEN.match(line)
        if match:
            if opening is None:
                opening = match.group(1)
            elif line.rstrip() == opening[0] * len(line.rstrip()) and len(
                line.rstrip()
            ) >= len(opening):
                opening = None
            continue
        if opening is None:
            out.append(line)
    return "\n".join(out)


def _v2_system_chars(content: str, teaching_brief: str) -> int:
    # lesson_entry.Engine uses sandbox rendering, read mode, and no extra
    # instructions. Mirror Engine.compose_instructions without importing the
    # optional pydantic-ai runtime into this read-only extractor.
    parts = ["system.md", "html_display.md"]
    # Engine.new_session detects 1.0 syntax in ScriptBundle.all_text(), which
    # includes both the script and the effective teaching brief.
    if _V1_SYNTAX.search(_outside_fenced_code(f"{content}\n{teaching_brief}")):
        parts.append("v1_syntax.md")
    return len(
        "\n\n".join(
            prompt
            for filename in parts
            if (prompt := (_ENGINE_PROMPTS_DIR / filename).read_text().strip())
        )
    )


def _v2_lesson_sizes(
    content: str, teaching_brief: str
) -> tuple[int, int, int, int, int]:
    # The agent sends the complete script in the first user message. Explicit
    # 1.0-style interactions still matter to its compatibility instructions;
    # ordinary prose that asks a question is not a machine-countable point.
    blocks = MarkdownFlow(content).get_all_blocks()
    interactions = sum(block.block_type == BlockType.INTERACTION for block in blocks)
    # ScriptBundle renders the inherited teaching brief as a constraints
    # section in the first user message. It remains in conversation history,
    # so count it alongside the fixed instructions rather than the script.
    brief = teaching_brief.strip()
    brief_chars = len(f"\n\n<constraints>\n{brief}\n</constraints>") if brief else 0
    return (
        len(content),
        0,
        _v2_system_chars(content, brief) + brief_chars,
        int(bool(content.strip())),
        interactions,
    )


def build_course_completion_credit_features(
    *,
    course: object,
    outline_items: list[DraftOutlineItem | PublishedOutlineItem] | list[object],
    visible_leaf_outline_bids: list[str] | set[str],
    engine: str,
    language: str,
) -> CourseCreditFeatures:
    """Build the whole-course feature vector for one engine/language cohort.

    `language` identifies the calibration cohort; it does not change authored
    character counts. Runtime learner-language courses should be classified as
    `und` by the caller until the target language is known.
    """
    if engine not in {"1.0", "2.0"}:
        message = f"unsupported teaching engine: {engine}"
        raise ValueError(message)
    if not language:
        message = "calibration language is required"
        raise ValueError(message)
    lessons, item_map = _selected_items(outline_items, visible_leaf_outline_bids)
    total_dynamic = total_static = total_system = 0
    total_blocks = total_interactions = 0
    char_square = chars_system = chars_blocks = 0.0

    for item in lessons:
        content = str(getattr(item, "content", "") or "")
        if not content.strip():
            message = "visible lesson has no teaching script"
            raise ValueError(message)
        if engine == "1.0":
            prompt = _effective_prompt(item, item_map, course)
            dynamic, static, system, blocks, interactions = _v1_lesson_sizes(
                content, prompt
            )
        else:
            prompt = _effective_prompt(
                item, item_map, course, max_ancestors=_V2_ANCESTOR_LIMIT
            )
            dynamic, static, system, blocks, interactions = _v2_lesson_sizes(
                content, prompt
            )
        total_dynamic += dynamic
        total_static += static
        total_system += system
        total_blocks += blocks
        total_interactions += interactions
        chars_k = (dynamic + static) / _THOUSAND
        system_k = system / _THOUSAND
        char_square += chars_k * chars_k
        chars_system += chars_k * system_k
        chars_blocks += (chars_k + system_k) * blocks

    return CourseCreditFeatures(
        lesson_count=float(len(lessons)),
        dynamic_chars_k=total_dynamic / _THOUSAND,
        static_chars_k=total_static / _THOUSAND,
        system_chars_k=total_system / _THOUSAND,
        generated_block_count=float(total_blocks),
        interaction_count=float(total_interactions),
        char_square_k2=char_square,
        chars_system_k2=chars_system,
        chars_blocks_k=chars_blocks,
    )


def detect_authored_language(
    outline_items: list[DraftOutlineItem | PublishedOutlineItem] | list[object],
    visible_leaf_outline_bids: list[str] | set[str],
) -> str:
    """Conservatively classify visible script language or return ``und``.

    This is only a cohort selector, so ambiguous or short scripts must not be
    forced into an English or Chinese calibration group.
    """
    lessons, _ = _selected_items(outline_items, visible_leaf_outline_bids)
    text = "\n".join(str(getattr(item, "content", "") or "") for item in lessons)
    text = _outside_fenced_code(text)
    # Common authoring markup is not natural language evidence.
    text = re.sub(r"https?://\S+|<[^>]+>|%?\{\{[^{}]+\}\}", " ", text)
    letters = [character for character in text if character.isalpha()]
    if len(letters) < 40:
        return "und"
    total = len(letters)
    scripts = {
        "zh": sum("\u3400" <= char <= "\u9fff" for char in letters),
        "ar": sum("\u0600" <= char <= "\u06ff" for char in letters),
        "th": sum("\u0e00" <= char <= "\u0e7f" for char in letters),
    }
    script, count = max(scripts.items(), key=lambda pair: pair[1])
    if count >= 24 and count / total >= 0.45:
        return script

    words = [word.casefold() for word in _LATIN_WORD.findall(text)]
    latin_letters = sum(
        "a" <= character.casefold() <= "z" or "\u00c0" <= character <= "\u024f"
        for character in letters
    )
    if len(words) < 20 or latin_letters / total < 0.7:
        return "und"
    french = sum(word in _FRENCH_WORDS for word in words)
    english = sum(word in _ENGLISH_WORDS for word in words)
    french_distinct = len(set(words) & _FRENCH_WORDS)
    english_distinct = len(set(words) & _ENGLISH_WORDS)
    if french >= 5 and french_distinct >= 3 and french >= 1.5 * english:
        return "fr"
    if english >= 5 and english_distinct >= 3 and english >= 1.5 * french:
        return "en"
    return "und"
