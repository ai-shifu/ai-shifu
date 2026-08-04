"""Operator course estimated full-course credit cost helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING

from flask import Flask

from flaskr.api.llm import get_current_models
from flaskr.api.tts import get_all_provider_configs
from flaskr.service.billing.api import (
    build_metric_charge,
    credit_decimal_to_number,
    resolve_credit_multiplier_label,
)
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_INPUT_CHARS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationEstimatedCreditAssumptionsDTO,
    AdminOperationEstimatedCreditComponentDTO,
    AdminOperationEstimatedCreditCostDTO,
    AdminOperationEstimatedCreditModeDTO,
)
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem
from flaskr.util.datetime import now_utc


_ZERO = Decimal("0")
_MARKDOWN_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_MARKERS_RE = re.compile(r"[>#*_~\-|]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class _CreditRange:
    minimum: Decimal
    maximum: Decimal

    def to_numbers(self) -> tuple[int | float, int | float]:
        return (
            credit_decimal_to_number(self.minimum),
            credit_decimal_to_number(self.maximum),
        )


@dataclass(frozen=True)
class _LlmEstimate:
    range: _CreditRange
    model: str
    model_label: str
    multiplier: str | None


@dataclass(frozen=True)
class _TtsEstimate:
    range: _CreditRange
    provider: str
    model: str
    model_label: str
    multiplier: str | None


@dataclass(frozen=True)
class _LessonCreditInputs:
    prompt_char_count: int
    content_char_count: int
    tts_char_count: int


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _strip_markdown_for_tts(value: str) -> str:
    text = _MARKDOWN_CODE_BLOCK_RE.sub(" ", str(value or ""))
    text = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _MARKDOWN_MARKERS_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _format_model_label_fallback(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    raw_label = "/".join(normalized.split("/")[1:]) if "/" in normalized else normalized
    return "-".join(
        segment[:1].upper() + segment[1:] if segment.isalpha() else segment
        for segment in raw_label.split("-")
        if segment
    )


def _resolve_llm_model_label(app: Flask, model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    try:
        for option in get_current_models(app):
            if str(option.get("model", "") or "").strip() == normalized:
                label = str(option.get("display_name", "") or "").strip()
                if label:
                    return label
    except Exception:
        pass
    return _format_model_label_fallback(normalized)


def _resolve_tts_model_label(provider: str, model: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    if not normalized_provider and not normalized_model:
        return ""
    try:
        options = get_all_provider_configs().get("model_options") or []
        for option in options:
            option_provider = str(option.get("provider", "") or "").strip().lower()
            option_model = str(option.get("model", "") or "").strip()
            if (
                option_provider == normalized_provider
                and option_model == normalized_model
            ):
                label = str(option.get("label", "") or "").strip()
                if label:
                    return label
        if normalized_model.startswith("speech-"):
            for option in options:
                if str(option.get("provider", "") or "").strip().lower() == "minimax":
                    label = str(option.get("label", "") or "").strip()
                    if label:
                        return label
        if normalized_model.startswith("seed-tts-"):
            for option in options:
                if (
                    str(option.get("provider", "") or "").strip().lower()
                    == "volcengine"
                ):
                    label = str(option.get("label", "") or "").strip()
                    if label:
                        return label
    except Exception:
        pass
    return _format_model_label_fallback(normalized_model or normalized_provider)


def _resolve_tts_model_multiplier_label(
    provider: str,
    model: str,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> str | None:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    try:
        options = get_all_provider_configs().get("model_options") or []
        provider_fallback: str | None = None
        for option in options:
            option_provider = str(option.get("provider", "") or "").strip().lower()
            option_model = str(option.get("model", "") or "").strip()
            credit_label = str(option.get("credit_multiplier_label", "") or "").strip()
            if option_provider != normalized_provider or not credit_label:
                continue
            if option_model == normalized_model:
                return credit_label
            if not option_model:
                provider_fallback = credit_label
        if provider_fallback:
            return provider_fallback
    except Exception:
        pass
    return resolve_credit_multiplier_label(
        usage_type=BILL_USAGE_TYPE_TTS,
        provider=normalized_provider,
        model=normalized_model,
        settlement_at=calculated_at,
        billing_metrics=(
            BILLING_METRIC_TTS_REQUEST_COUNT,
            BILLING_METRIC_TTS_OUTPUT_CHARS,
            BILLING_METRIC_TTS_INPUT_CHARS,
        ),
        rate_cache=rate_cache,
    )


def _estimate_metric_credits(
    *,
    usage_type: int,
    provider: str,
    model: str,
    billing_metric: int,
    raw_amount: int,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> Decimal:
    consumed = _estimate_metric_credits_optional(
        usage_type=usage_type,
        provider=provider,
        model=model,
        billing_metric=billing_metric,
        raw_amount=raw_amount,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    return consumed if consumed is not None else _ZERO


def _estimate_metric_credits_optional(
    *,
    usage_type: int,
    provider: str,
    model: str,
    billing_metric: int,
    raw_amount: int,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> Decimal | None:
    if raw_amount <= 0:
        return None
    usage = BillUsageRecord(
        usage_type=usage_type,
        provider=provider,
        model=model,
        usage_scene=BILL_USAGE_SCENE_PROD,
    )
    charge = build_metric_charge(
        usage,
        billing_metric=billing_metric,
        raw_amount=raw_amount,
        settlement_at=calculated_at,
        rate_cache=rate_cache,
    )
    if charge is None:
        return None
    return Decimal(str(charge.consumed_credits))


def _estimate_llm_cost(
    *,
    app: Flask,
    model: str,
    prompt_char_count: int,
    content_char_count: int,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> _LlmEstimate:
    normalized_model = str(model or "").strip()
    input_tokens = _ceil_decimal(
        Decimal(str(prompt_char_count + content_char_count)) / Decimal("2")
    )
    output_low = _ceil_decimal(Decimal(str(input_tokens)) * Decimal("0.6"))
    output_high = _ceil_decimal(Decimal(str(input_tokens)) * Decimal("1.5"))
    input_cost = _estimate_metric_credits(
        usage_type=BILL_USAGE_TYPE_LLM,
        provider="",
        model=normalized_model,
        billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
        raw_amount=input_tokens,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    low = input_cost + _estimate_metric_credits(
        usage_type=BILL_USAGE_TYPE_LLM,
        provider="",
        model=normalized_model,
        billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        raw_amount=output_low,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    high = input_cost + _estimate_metric_credits(
        usage_type=BILL_USAGE_TYPE_LLM,
        provider="",
        model=normalized_model,
        billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        raw_amount=output_high,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    return _LlmEstimate(
        range=_CreditRange(low, high),
        model=normalized_model,
        model_label=_resolve_llm_model_label(app, normalized_model),
        multiplier=resolve_credit_multiplier_label(
            usage_type=BILL_USAGE_TYPE_LLM,
            provider="",
            model=normalized_model,
            settlement_at=calculated_at,
            rate_cache=rate_cache,
        ),
    )


def _sum_llm_cost(
    *,
    app: Flask,
    model: str,
    lesson_inputs: list[_LessonCreditInputs],
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> _LlmEstimate:
    normalized_model = str(model or "").strip()
    total = _CreditRange(_ZERO, _ZERO)
    for item in lesson_inputs:
        estimate = _estimate_llm_cost(
            app=app,
            model=normalized_model,
            prompt_char_count=item.prompt_char_count,
            content_char_count=item.content_char_count,
            calculated_at=calculated_at,
            rate_cache=rate_cache,
        )
        total = _CreditRange(
            total.minimum + estimate.range.minimum,
            total.maximum + estimate.range.maximum,
        )
    return _LlmEstimate(
        range=total,
        model=normalized_model,
        model_label=_resolve_llm_model_label(app, normalized_model),
        multiplier=resolve_credit_multiplier_label(
            usage_type=BILL_USAGE_TYPE_LLM,
            provider="",
            model=normalized_model,
            settlement_at=calculated_at,
            rate_cache=rate_cache,
        ),
    )


def _estimate_tts_cost(
    *,
    provider: str,
    model: str,
    tts_char_count: int,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> _TtsEstimate:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    low_chars = _ceil_decimal(Decimal(str(tts_char_count)) * Decimal("0.9"))
    high_chars = _ceil_decimal(Decimal(str(tts_char_count)) * Decimal("1.1"))
    low = _estimate_tts_credits_with_metric_priority(
        provider=normalized_provider,
        model=normalized_model,
        request_count=1,
        input_chars=tts_char_count,
        output_chars=low_chars,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    high = _estimate_tts_credits_with_metric_priority(
        provider=normalized_provider,
        model=normalized_model,
        request_count=1,
        input_chars=tts_char_count,
        output_chars=high_chars,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )
    return _TtsEstimate(
        range=_CreditRange(low, high),
        provider=normalized_provider,
        model=normalized_model,
        model_label=_resolve_tts_model_label(normalized_provider, normalized_model),
        multiplier=_resolve_tts_model_multiplier_label(
            normalized_provider, normalized_model, calculated_at, rate_cache
        ),
    )


def _estimate_tts_credits_with_metric_priority(
    *,
    provider: str,
    model: str,
    request_count: int,
    input_chars: int,
    output_chars: int,
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> Decimal:
    for billing_metric, raw_amount in (
        (BILLING_METRIC_TTS_REQUEST_COUNT, request_count),
        (BILLING_METRIC_TTS_OUTPUT_CHARS, output_chars),
        (BILLING_METRIC_TTS_INPUT_CHARS, input_chars),
    ):
        consumed = _estimate_metric_credits_optional(
            usage_type=BILL_USAGE_TYPE_TTS,
            provider=provider,
            model=model,
            billing_metric=billing_metric,
            raw_amount=raw_amount,
            calculated_at=calculated_at,
            rate_cache=rate_cache,
        )
        if consumed is not None:
            return consumed
    return _ZERO


def _sum_tts_cost(
    *,
    provider: str,
    model: str,
    lesson_inputs: list[_LessonCreditInputs],
    calculated_at: datetime,
    rate_cache: dict | None = None,
) -> _TtsEstimate:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    total = _CreditRange(_ZERO, _ZERO)
    for item in lesson_inputs:
        estimate = _estimate_tts_cost(
            provider=normalized_provider,
            model=normalized_model,
            tts_char_count=item.tts_char_count,
            calculated_at=calculated_at,
            rate_cache=rate_cache,
        )
        total = _CreditRange(
            total.minimum + estimate.range.minimum,
            total.maximum + estimate.range.maximum,
        )
    return _TtsEstimate(
        range=total,
        provider=normalized_provider,
        model=normalized_model,
        model_label=_resolve_tts_model_label(normalized_provider, normalized_model),
        multiplier=_resolve_tts_model_multiplier_label(
            normalized_provider, normalized_model, calculated_at, rate_cache
        ),
    )


def _build_component(
    estimate: _LlmEstimate | _TtsEstimate,
) -> AdminOperationEstimatedCreditComponentDTO:
    minimum, maximum = estimate.range.to_numbers()
    return AdminOperationEstimatedCreditComponentDTO(
        min=minimum,
        max=maximum,
        model=estimate.model,
        model_label=estimate.model_label,
        multiplier=estimate.multiplier,
    )


def _build_mode(
    *,
    llm: _LlmEstimate,
    tts: _TtsEstimate | None = None,
    enabled: bool | None = None,
) -> AdminOperationEstimatedCreditModeDTO:
    minimum = llm.range.minimum + (tts.range.minimum if tts is not None else _ZERO)
    maximum = llm.range.maximum + (tts.range.maximum if tts is not None else _ZERO)
    min_number, max_number = _CreditRange(minimum, maximum).to_numbers()
    return AdminOperationEstimatedCreditModeDTO(
        min=min_number,
        max=max_number,
        llm=_build_component(llm),
        tts=_build_component(tts) if tts is not None else None,
        enabled=enabled,
    )


def build_operator_course_estimated_credit_cost(
    app: Flask,
    *,
    course,
    outline_items: list[DraftOutlineItem | PublishedOutlineItem],
    visible_leaf_outline_bids: list[str] | set[str],
) -> AdminOperationEstimatedCreditCostDTO:
    calculated_at = now_utc()
    rate_cache: dict = {}
    item_map = {
        str(getattr(item, "outline_item_bid", "") or "").strip(): item
        for item in outline_items
        if str(getattr(item, "outline_item_bid", "") or "").strip()
    }
    visible_leaf_items = [
        item_map[bid]
        for bid in sorted(
            {
                str(outline_item_bid or "").strip()
                for outline_item_bid in visible_leaf_outline_bids
            }
        )
        if bid in item_map
    ]

    course_prompt = str(getattr(course, "llm_system_prompt", "") or "").strip()
    prompt_char_count = 0
    content_char_count = 0
    tts_char_count = 0
    lesson_inputs: list[_LessonCreditInputs] = []
    for item in visible_leaf_items:
        prompt = str(getattr(item, "llm_system_prompt", "") or "").strip()
        parent_bid = str(getattr(item, "parent_bid", "") or "").strip()
        visited = {str(getattr(item, "outline_item_bid", "") or "").strip()}
        while not prompt and parent_bid and parent_bid not in visited:
            visited.add(parent_bid)
            parent = item_map.get(parent_bid)
            if parent is None:
                break
            prompt = str(getattr(parent, "llm_system_prompt", "") or "").strip()
            parent_bid = str(getattr(parent, "parent_bid", "") or "").strip()
        if not prompt:
            prompt = course_prompt
        content = str(getattr(item, "content", "") or "")
        item_prompt_char_count = len(prompt)
        item_content_char_count = len(content)
        item_tts_char_count = len(_strip_markdown_for_tts(content))
        prompt_char_count += item_prompt_char_count
        content_char_count += item_content_char_count
        tts_char_count += item_tts_char_count
        lesson_inputs.append(
            _LessonCreditInputs(
                prompt_char_count=item_prompt_char_count,
                content_char_count=item_content_char_count,
                tts_char_count=item_tts_char_count,
            )
        )

    llm_model = str(getattr(course, "llm", "") or "").strip()
    if not llm_model:
        llm_model = str(app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
    llm = _sum_llm_cost(
        app=app,
        model=llm_model,
        lesson_inputs=lesson_inputs,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )

    tts = _sum_tts_cost(
        provider=str(getattr(course, "tts_provider", "") or "").strip(),
        model=str(getattr(course, "tts_model", "") or "").strip(),
        lesson_inputs=lesson_inputs,
        calculated_at=calculated_at,
        rate_cache=rate_cache,
    )

    return AdminOperationEstimatedCreditCostDTO(
        read=_build_mode(llm=llm),
        listen=_build_mode(
            llm=llm,
            tts=tts,
            enabled=bool(int(getattr(course, "tts_enabled", 0) or 0)),
        ),
        classroom=_build_mode(llm=llm),
        assumptions=AdminOperationEstimatedCreditAssumptionsDTO(
            visible_lesson_count=len(visible_leaf_items),
            prompt_char_count=prompt_char_count,
            content_char_count=content_char_count,
            calculated_at=calculated_at,
        ),
    )
