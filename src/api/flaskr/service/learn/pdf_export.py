from __future__ import annotations

from html import escape
from pathlib import Path
import re
import subprocess
import tempfile
import time

from flask import Flask
from markdown_flow import InteractionParser

from flaskr.service.common import raise_error, raise_param_error
from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
from flaskr.service.learn.learn_funcs import get_shifu_info
from flaskr.service.learn.lesson_feedback import is_lesson_feedback_interaction
from flaskr.service.learn.listen_elements import get_listen_element_record
from flaskr.service.learn.pdf_export_models import (
    PdfExportBlock,
    PdfExportDocument,
    PdfExportInteraction,
    PdfExportInteractionButton,
    PdfExportResult,
    PdfExportWatermark,
)
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem


PDF_EXPORT_FOLLOW_UP_QUESTION_LABEL = "追问"
PDF_EXPORT_FOLLOW_UP_ANSWER_LABEL = "追问回答"
PDF_EXPORT_BRAND_NAME = "AI 师傅"
PDF_EXPORT_INTERACTION_CHOICE_LABEL = "互动选择"
PDF_EXPORT_INTERACTION_INPUT_LABEL = "互动输入"
PDF_EXPORT_INTERACTION_SELECTED_LABEL = "已选"
PDF_EXPORT_INTERACTION_RESPONSE_LABEL = "你的输入"
PDF_EXPORT_DEFAULT_TTL_SECONDS = 3 * 60 * 60
PDF_EXPORT_TEMP_DIR_PREFIX = "learn_pdf_export_"
PDF_EXPORT_HTML_TARGET_WIDTH_PX = 680
_PDF_EXPORT_SKIPPED_INTERACTION_VALUES = {
    "_sys_next_chapter",
    "_sys_login",
    "_sys_pay",
}
_PDF_EXPORT_MIN_HEIGHT_PATTERN = re.compile(
    r"min-height\s*:\s*[^;\"']+;?",
    re.IGNORECASE,
)
_PDF_EXPORT_HEIGHT_PATTERN = re.compile(
    r"(?<!min-)height\s*:\s*(?:100vh|100dvh|100svh|100lvh|100vw)[^;\"']*;?",
    re.IGNORECASE,
)
_PDF_EXPORT_OVERFLOW_PATTERN = re.compile(
    r"overflow-(?:x|y)\s*:\s*[^;\"']+;?",
    re.IGNORECASE,
)
_PDF_EXPORT_FLEX_ALIGN_PATTERN = re.compile(
    r"(?:display\s*:\s*flex|align-items\s*:\s*center|justify-content\s*:\s*center);?",
    re.IGNORECASE,
)
_PDF_EXPORT_MAX_WIDTH_PATTERN = re.compile(
    r"max-width\s*:\s*(\d+)px",
    re.IGNORECASE,
)
_PDF_EXPORT_CLAMP_FONT_SIZE_PATTERN = re.compile(
    r"font-size\s*:\s*clamp\([^)]*100vw\s*/\s*([0-9.]+)[^)]*\)",
    re.IGNORECASE,
)

_EXPORTABLE_ELEMENT_TYPES = {
    ElementType.TITLE,
    ElementType.TEXT,
    ElementType.CODE,
    ElementType.TABLES,
    ElementType.HTML,
    ElementType.LATEX,
    ElementType.ASK,
    ElementType.ANSWER,
    ElementType.INTERACTION,
    ElementType.MERMAID,
    ElementType.SVG,
    ElementType.IMG,
    ElementType.MD_IMG,
}


def export_lesson_pdf(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
) -> PdfExportResult:
    temp_dir = build_pdf_temp_dir(app)
    record = load_lesson_export_record(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        preview_mode=preview_mode,
    )
    document = build_pdf_export_document(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        preview_mode=preview_mode,
        record=record,
        temp_dir=temp_dir,
    )
    html = render_pdf_html(document)
    download_name = build_pdf_file_name(document)
    file_path = str(Path(temp_dir) / download_name)
    generate_pdf_file(html=html, file_path=file_path)
    return PdfExportResult(
        file_path=file_path,
        download_name=download_name,
        temp_dir=temp_dir,
    )


def load_lesson_export_record(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
):
    return get_listen_element_record(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        preview_mode=preview_mode,
        include_non_navigable=False,
    )


def build_pdf_export_document(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
    record,
    temp_dir: str,
) -> PdfExportDocument:
    course_info = get_shifu_info(app, shifu_bid, preview_mode)
    lesson_name = resolve_lesson_title(
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        preview_mode=preview_mode,
    )
    blocks = filter_exportable_elements(
        record.elements or [],
        temp_dir=temp_dir,
    )
    if not blocks:
        raise_param_error("lesson_content")
    watermark = PdfExportWatermark(
        brand_name=PDF_EXPORT_BRAND_NAME,
        course_name=course_info.title,
        lesson_name=lesson_name,
    )
    return PdfExportDocument(
        course_bid=shifu_bid,
        lesson_bid=outline_bid,
        course_name=course_info.title,
        lesson_name=lesson_name,
        preview_mode=preview_mode,
        watermark=watermark,
        blocks=blocks,
    )


def resolve_lesson_title(*, shifu_bid: str, outline_bid: str, preview_mode: bool) -> str:
    model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    outline_item = (
        model.query.filter(
            model.shifu_bid == shifu_bid,
            model.outline_item_bid == outline_bid,
            model.deleted == 0,
        )
        .order_by(model.id.desc())
        .first()
    )
    if not outline_item:
        raise_error("server.shifu.outlineItemNotFound")
    return str(outline_item.title or "").strip()


def filter_exportable_elements(
    elements: list[ElementDTO],
    *,
    temp_dir: str | None = None,
) -> list[PdfExportBlock]:
    blocks: list[PdfExportBlock] = []
    for index, element in enumerate(elements or []):
        block = map_element_to_pdf_block(
            element,
            order=index,
            temp_dir=temp_dir,
        )
        if block is None:
            continue
        blocks.append(block)
    return blocks


def map_element_to_pdf_block(
    element: ElementDTO,
    *,
    order: int,
    temp_dir: str | None = None,
) -> PdfExportBlock | None:
    if not element:
        return None

    element_type = element.element_type
    if element_type not in _EXPORTABLE_ELEMENT_TYPES:
        return None

    content = str(element.content or "").strip()
    if not content:
        return None

    if not _should_export_element(element, content=content):
        return None

    label = ""
    is_follow_up = False
    block_type = element_type.value
    interaction = None

    if element_type == ElementType.INTERACTION:
        interaction = _build_pdf_interaction(element, content=content)
        if interaction is None:
            return None
    elif element_type == ElementType.ASK:
        label = PDF_EXPORT_FOLLOW_UP_QUESTION_LABEL
        is_follow_up = True
    elif element_type == ElementType.ANSWER:
        label = PDF_EXPORT_FOLLOW_UP_ANSWER_LABEL
        is_follow_up = True
    elif element_type == ElementType.TITLE:
        content = re.sub(r"^#+\s*", "", content).strip() or content
    elif element_type in {
        ElementType.HTML,
        ElementType.TABLES,
        ElementType.SVG,
        ElementType.IMG,
        ElementType.MD_IMG,
    }:
        content = _prepare_pdf_visual_content(
            content,
            element_type=element_type,
            order=order,
            temp_dir=temp_dir,
        )

    return PdfExportBlock(
        block_type=block_type,
        content=content,
        order=order,
        label=label,
        is_follow_up=is_follow_up,
        interaction=interaction,
    )


def _should_export_element(element: ElementDTO, *, content: str) -> bool:
    element_type = element.element_type
    is_renderable = bool(getattr(element, "is_renderable", False))
    is_marker = bool(getattr(element, "is_marker", False))

    if element_type == ElementType.INTERACTION:
        return bool(content)

    # Historical and newly generated learn records both contain readable content,
    # but they do not use the same renderable/marker flags consistently.
    if element_type in {
        ElementType.TEXT,
        ElementType.CODE,
        ElementType.TABLES,
        ElementType.HTML,
        ElementType.LATEX,
        ElementType.MERMAID,
        ElementType.SVG,
        ElementType.IMG,
        ElementType.MD_IMG,
        ElementType.TITLE,
        ElementType.ASK,
        ElementType.ANSWER,
    }:
        return bool(content)

    return is_renderable and not is_marker


def _build_pdf_interaction(
    element: ElementDTO,
    *,
    content: str,
) -> PdfExportInteraction | None:
    if is_lesson_feedback_interaction(content):
        return None

    parsed = _parse_interaction_content(content)
    if not parsed:
        return None

    interaction_type = _normalize_interaction_type(parsed.get("type"))
    buttons = parsed.get("buttons") or []
    if _should_skip_pdf_interaction(buttons):
        return None
    button_values = {
        str(button.get("value", "") or "").strip()
        for button in buttons
        if isinstance(button, dict)
    }
    selected_values, input_value = _resolve_interaction_user_input(
        interaction_type=interaction_type,
        raw_user_input=getattr(getattr(element, "payload", None), "user_input", None),
        button_values=button_values,
    )

    interaction_buttons = []
    for button in buttons:
        if not isinstance(button, dict):
            continue
        value = str(button.get("value", "") or "").strip()
        label = str(button.get("display", value) or value).strip()
        interaction_buttons.append(
            PdfExportInteractionButton(
                label=label,
                value=value,
                selected=value in selected_values or label in selected_values,
            )
        )

    interaction = PdfExportInteraction(
        interaction_type=interaction_type,
        buttons=interaction_buttons,
        input_placeholder=str(parsed.get("question", "") or "").strip(),
        input_value=input_value,
        is_multi_select=bool(parsed.get("is_multi_select", False)),
    )
    if not _has_visible_pdf_interaction_content(interaction):
        return None
    return interaction


def _has_visible_pdf_interaction_content(interaction: PdfExportInteraction) -> bool:
    if interaction.interaction_type == "text_only":
        return bool(str(interaction.input_value or "").strip())
    if interaction.buttons:
        return True
    if str(interaction.input_value or "").strip():
        return True
    return False


def _should_skip_pdf_interaction(buttons: list[dict]) -> bool:
    normalized_values = {
        str(button.get("value", "") or "").strip()
        for button in buttons
        if isinstance(button, dict)
    }
    if not normalized_values:
        return False
    return normalized_values.issubset(_PDF_EXPORT_SKIPPED_INTERACTION_VALUES)


def _parse_interaction_content(content: str) -> dict | None:
    try:
        parsed = InteractionParser().parse(content)
    except Exception:
        parsed = None
    if parsed and parsed.get("type"):
        return parsed
    return _parse_legacy_button_interaction(content)


def _parse_legacy_button_interaction(content: str) -> dict | None:
    normalized = str(content or "").strip()
    if not normalized.startswith("?["):
        return None

    matches = re.findall(r"\[([^\]]+)\]", normalized)
    if not matches:
        return None

    buttons = []
    for raw_button in matches:
        text = str(raw_button or "").strip()
        if not text:
            continue
        display, _, value = text.partition("//")
        buttons.append(
            {
                "display": display.strip(),
                "value": (value or display).strip(),
            }
        )

    if not buttons:
        return None

    return {
        "type": "non_assignment_button",
        "buttons": buttons,
        "is_multi_select": False,
    }


def _resolve_interaction_user_input(
    *,
    interaction_type: str,
    raw_user_input: str | None,
    button_values: set[str],
) -> tuple[set[str], str]:
    interaction_type = _normalize_interaction_type(interaction_type)
    normalized = str(raw_user_input or "").strip()
    if not normalized:
        return set(), ""

    if interaction_type == "text_only":
        return set(), normalized

    fragments = [
        fragment.strip()
        for fragment in re.split(r",|\n|，", normalized)
        if fragment and fragment.strip()
    ]
    if not fragments:
        return set(), normalized

    selected_values = {fragment for fragment in fragments if fragment in button_values}
    remaining_fragments = [
        fragment for fragment in fragments if fragment not in selected_values
    ]

    if interaction_type == "buttons_with_text":
        return selected_values, ", ".join(remaining_fragments)
    if interaction_type in {"buttons_only", "buttons_multi_select"}:
        return selected_values, ""
    if interaction_type == "non_assignment_button":
        return set(fragments), ""
    return selected_values, ", ".join(remaining_fragments)


def _normalize_interaction_type(value: object) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered.startswith("interactiontype."):
        return lowered.split(".", 1)[1]
    return lowered


def _sanitize_pdf_html_block(content: str) -> str:
    sanitized = str(content or "")
    if not sanitized:
        return sanitized

    def _rewrite_style(match: re.Match[str]) -> str:
        quote = match.group(1)
        styles = match.group(2)
        cleaned = _PDF_EXPORT_MIN_HEIGHT_PATTERN.sub("", styles)
        cleaned = _PDF_EXPORT_HEIGHT_PATTERN.sub("", cleaned)
        cleaned = _PDF_EXPORT_OVERFLOW_PATTERN.sub("", cleaned)
        cleaned = _PDF_EXPORT_FLEX_ALIGN_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r";\s*;", ";", cleaned)
        cleaned = cleaned.strip(" ;")
        if not cleaned:
            return ""
        return f'style={quote}{cleaned}{quote}'

    sanitized = re.sub(
        r'style=(["\'])(.*?)\1',
        _rewrite_style,
        sanitized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return sanitized


def _prepare_pdf_visual_content(
    content: str,
    *,
    element_type: ElementType,
    order: int,
    temp_dir: str | None,
) -> str:
    normalized = _sanitize_pdf_html_block(content)
    if element_type != ElementType.HTML:
        return normalized
    normalized_layout = _normalize_visual_html_layout(normalized)
    if not temp_dir or not _should_rasterize_html_block(normalized):
        return normalized_layout
    try:
        return _rasterize_html_block_to_img_tag(
            normalized,
            order=order,
            temp_dir=temp_dir,
        )
    except Exception:
        return normalized_layout


def _normalize_visual_html_layout(content: str) -> str:
    width_match = _PDF_EXPORT_MAX_WIDTH_PATTERN.search(content)
    if not width_match:
        return content

    original_width = int(width_match.group(1) or 0)
    if original_width <= PDF_EXPORT_HTML_TARGET_WIDTH_PX:
        return content

    scale = PDF_EXPORT_HTML_TARGET_WIDTH_PX / float(original_width)
    normalized = _PDF_EXPORT_MAX_WIDTH_PATTERN.sub(
        f"max-width:{PDF_EXPORT_HTML_TARGET_WIDTH_PX}px",
        content,
        count=1,
    )

    def _replace_clamp_font(match: re.Match[str]) -> str:
        divisor = float(match.group(1) or 0)
        if divisor <= 0:
            return match.group(0)
        scaled_base = max(10.0, round(PDF_EXPORT_HTML_TARGET_WIDTH_PX / divisor, 2))
        return f"font-size:{scaled_base}px"

    normalized = _PDF_EXPORT_CLAMP_FONT_SIZE_PATTERN.sub(
        _replace_clamp_font,
        normalized,
        count=1,
    )
    return (
        f'<div class="pdf-visual-card" style="--pdf-visual-scale:{scale:.4f};">'
        f"{normalized}</div>"
    )


def _should_rasterize_html_block(content: str) -> bool:
    normalized = str(content or "")
    if "linear-gradient(" not in normalized:
        return False
    return "max-width:" in normalized and "font-size:clamp(" in normalized


def _rasterize_html_block_to_img_tag(
    content: str,
    *,
    order: int,
    temp_dir: str,
) -> str:
    temp_root = Path(temp_dir)
    html_path = temp_root / f"visual-card-{order}.html"
    png_path = temp_root / f"visual-card-{order}.png"
    html_path.write_text(content, encoding="utf-8")

    repo_root, script_path = _resolve_pdf_html_renderer_script()
    command = [
        "node",
        str(script_path),
        str(html_path),
        str(png_path),
        "1280",
    ]
    try:
        subprocess.run(
            command,
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to rasterize lesson html block for PDF export: {exc.stderr or exc.stdout}"
        ) from exc

    return (
        '<img class="pdf-rasterized-visual" src="{src}" alt="lesson visual" />'.format(
            src=png_path.resolve().as_uri()
        )
    )


def _resolve_pdf_html_renderer_script() -> tuple[Path, Path]:
    current = Path(__file__).resolve()
    candidates = [
        (
            current.parents[3],
            current.parents[3] / "scripts/render_pdf_html_card.mjs",
        ),
    ]
    if len(current.parents) > 5:
        candidates.append(
            (
                current.parents[5],
                current.parents[5] / "src/api/scripts/render_pdf_html_card.mjs",
            )
        )
    for repo_root, script_path in candidates:
        if script_path.exists():
            return repo_root, script_path
    raise RuntimeError("PDF HTML renderer script not found")


def render_pdf_html(document: PdfExportDocument) -> str:
    rendered_blocks = "\n".join(
        _render_pdf_block(block) for block in document.blocks if block.content
    )
    watermark_text = " / ".join(
        [
            escape(document.watermark.brand_name),
            escape(document.watermark.course_name),
            escape(document.watermark.lesson_name),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>{escape(document.course_name)} - {escape(document.lesson_name)}</title>
    <style>
      @page {{
        size: A4;
        margin: 18mm 16mm 18mm 16mm;
      }}
      body {{
        color: #111827;
        font-family: "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans CN", "WenQuanYi Zen Hei", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: 14px;
        line-height: 1.65;
        margin: 0;
      }}
      .watermark {{
        color: rgba(71, 85, 105, 0.24);
        font-size: 34px;
        font-weight: 700;
        left: 50%;
        letter-spacing: 1px;
        pointer-events: none;
        position: fixed;
        text-align: center;
        top: 48%;
        transform: translate(-50%, -50%) rotate(-24deg);
        width: 90%;
        z-index: 999;
      }}
      .page {{
        position: relative;
        z-index: 1;
      }}
      .header {{
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 20px;
        padding-bottom: 12px;
      }}
      .course {{
        color: #374151;
        font-size: 24px;
        font-weight: 700;
        margin: 0 0 8px;
      }}
      .lesson {{
        color: #6b7280;
        font-size: 14px;
        font-weight: 600;
        margin: 0;
      }}
      .block {{
        border-radius: 12px;
        margin-bottom: 14px;
        break-inside: auto;
        page-break-inside: auto;
      }}
      .block-follow-up {{
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        break-inside: avoid;
        page-break-inside: avoid;
        padding: 12px 14px;
      }}
      .block-follow-up-question {{
        border-left: 4px solid #60a5fa;
      }}
      .block-follow-up-answer {{
        border-left: 4px solid #34d399;
      }}
      .block-title {{
        font-size: 18px;
        font-weight: 700;
        margin: 18px 0 10px;
      }}
      .block-label {{
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 999px;
        color: #1d4ed8;
        display: inline-block;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 8px;
        padding: 2px 10px;
      }}
      .block-pre {{
        background: #0f172a;
        break-inside: avoid;
        border-radius: 10px;
        color: #e2e8f0;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 12px;
        overflow-wrap: anywhere;
        page-break-inside: avoid;
        padding: 12px 14px;
        white-space: pre-wrap;
      }}
      .block-html, .block-text {{
        white-space: pre-wrap;
        word-break: break-word;
        overflow-wrap: anywhere;
      }}
      .block-html {{
        line-height: 1.68;
      }}
      .block-html .pdf-visual-card {{
        break-inside: avoid;
        margin: 0 auto;
        page-break-inside: avoid;
        width: 100%;
      }}
      .block-html .pdf-visual-card > * {{
        margin-left: auto;
        margin-right: auto;
      }}
      .block-html .pdf-rasterized-visual {{
        display: block;
        height: auto;
        margin: 0 auto;
        max-width: 100%;
      }}
      .block-html > *:first-child {{
        margin-top: 0 !important;
      }}
      .block-html > *:last-child {{
        margin-bottom: 0 !important;
      }}
      .block-html * {{
        box-sizing: border-box;
        max-width: 100% !important;
      }}
      .block-html [style*="min-height"],
      .block-html [style*="height:"] {{
        height: auto !important;
        min-height: 0 !important;
      }}
      .block-html p,
      .block-html ul,
      .block-html ol,
      .block-html table,
      .block-html pre,
      .block-html blockquote {{
        break-inside: auto;
        page-break-inside: auto;
      }}
      .block-html table {{
        border-collapse: collapse;
        width: 100%;
      }}
      .block-html th, .block-html td {{
        border: 1px solid #d1d5db;
        padding: 6px 8px;
        vertical-align: top;
      }}
      .block-html img, .block-html svg {{
        break-inside: avoid;
        max-width: 100%;
        page-break-inside: avoid;
      }}
      .block-interaction {{
        background: #f8fbff;
        border: 1px solid #dbeafe;
        border-radius: 16px;
        break-inside: avoid;
        box-shadow: none;
        page-break-inside: avoid;
        padding: 18px 20px 18px;
      }}
      .interaction-shell {{
        display: block;
      }}
      .interaction-heading {{
        align-items: center;
        color: #1d4ed8;
        display: inline-flex;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 14px;
        padding: 4px 10px;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 999px;
      }}
      .interaction-options {{
        display: block;
        margin-bottom: 10px;
      }}
      .interaction-option {{
        align-items: start;
        background: #ffffff;
        border: 1px solid #dbe4f0;
        border-radius: 12px;
        break-inside: avoid;
        color: #111827;
        display: grid;
        grid-template-columns: 18px minmax(0, 1fr);
        font-size: 15px;
        font-weight: 500;
        gap: 10px;
        line-height: 1.55;
        margin-bottom: 10px;
        padding: 10px 12px;
        page-break-inside: avoid;
      }}
      .interaction-option-indicator {{
        color: #94a3b8;
        display: block;
        font-size: 15px;
        font-weight: 700;
        line-height: 1.4;
        margin-top: 1px;
        text-align: center;
        width: 18px;
      }}
      .interaction-option-label {{
        display: block;
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      .interaction-option-status {{
        color: #2563eb;
        display: inline-block;
        font-size: 12px;
        font-weight: 700;
        margin-left: 8px;
      }}
      .interaction-input-row {{
        align-items: stretch;
        display: block;
        gap: 12px;
      }}
      .interaction-response-label {{
        color: #1d4ed8;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 8px;
      }}
      .interaction-input-shell {{
        align-items: center;
        background: #ffffff;
        border: 1.5px solid #cbd5e1;
        border-radius: 12px;
        box-shadow: none;
        display: flex;
        flex: 1 1 auto;
        justify-content: space-between;
        min-height: 48px;
        padding: 0 12px 0 14px;
      }}
      .interaction-input-value {{
        color: #111827;
        flex: 1 1 auto;
        font-size: 15px;
        font-weight: 500;
        line-height: 1.4;
        overflow-wrap: anywhere;
        padding: 12px 10px 12px 0;
      }}
      .interaction-input-placeholder {{
        color: #9ca3af;
      }}
      .interaction-send {{
        display: none;
      }}
    </style>
  </head>
  <body>
    <div class="watermark">{watermark_text}</div>
    <main class="page">
      <header class="header">
        <h1 class="course">{escape(document.course_name)}</h1>
        <p class="lesson">{escape(document.lesson_name)}</p>
      </header>
      {rendered_blocks}
    </main>
  </body>
</html>
"""


def _render_pdf_block(block: PdfExportBlock) -> str:
    label_html = (
        f'<div class="block-label">{escape(block.label)}</div>' if block.label else ""
    )
    block_classes = ["block", f"block-{escape(block.block_type)}"]
    if block.is_follow_up:
        block_classes.append("block-follow-up")
    if block.label == PDF_EXPORT_FOLLOW_UP_QUESTION_LABEL:
        block_classes.append("block-follow-up-question")
    elif block.label == PDF_EXPORT_FOLLOW_UP_ANSWER_LABEL:
        block_classes.append("block-follow-up-answer")
    class_attr = " ".join(block_classes)
    if block.block_type == ElementType.TITLE.value:
        return (
            f'<section class="{class_attr}">{label_html}'
            f'<h2 class="block-title">{escape(block.content)}</h2></section>'
        )
    if block.block_type == ElementType.CODE.value:
        return (
            f'<section class="{class_attr}">{label_html}'
            f'<pre class="block-pre">{escape(block.content)}</pre></section>'
        )
    if block.block_type == ElementType.INTERACTION.value and block.interaction is not None:
        return (
            f'<section class="{class_attr}">'
            f"{_render_pdf_interaction(block.interaction)}</section>"
        )
    if block.block_type in {
        ElementType.HTML.value,
        ElementType.TABLES.value,
        ElementType.SVG.value,
        ElementType.IMG.value,
        ElementType.MD_IMG.value,
    }:
        return (
            f'<section class="{class_attr}">{label_html}'
            f'<div class="block-html">{block.content}</div></section>'
        )
    return (
        f'<section class="{class_attr}">{label_html}'
        f'<div class="block-text">{escape(block.content)}</div></section>'
    )


def _render_pdf_interaction(interaction: PdfExportInteraction) -> str:
    interaction_type = _normalize_interaction_type(interaction.interaction_type)
    if interaction_type == "text_only":
        return (
            f'<div class="interaction-shell"><div class="interaction-heading">'
            f"{escape(PDF_EXPORT_INTERACTION_INPUT_LABEL)}</div>"
            f"{_render_pdf_interaction_input(input_value=interaction.input_value, input_placeholder=interaction.input_placeholder)}</div>"
        )
    if interaction_type == "buttons_with_text":
        return (
            f'<div class="interaction-shell"><div class="interaction-heading">'
            f"{escape(PDF_EXPORT_INTERACTION_CHOICE_LABEL)}</div>"
            f"{_render_pdf_interaction_buttons(interaction)}"
            f'{_render_pdf_interaction_input(input_value=interaction.input_value, input_placeholder=interaction.input_placeholder, compact=True)}</div>'
        )
    return (
        f'<div class="interaction-shell"><div class="interaction-heading">'
        f"{escape(PDF_EXPORT_INTERACTION_CHOICE_LABEL)}</div>"
        f"{_render_pdf_interaction_buttons(interaction)}"
        "</div>"
    )


def _render_pdf_interaction_buttons(interaction: PdfExportInteraction) -> str:
    rendered = []
    for button in interaction.buttons:
        indicator = "&#10003;" if button.selected else "&#9675;"
        selected_html = (
            f'<span class="interaction-option-status">{escape(PDF_EXPORT_INTERACTION_SELECTED_LABEL)}</span>'
            if button.selected
            else ""
        )
        rendered.append(
            '<div class="interaction-option"><span class="interaction-option-indicator">{indicator}</span>'
            '<span class="interaction-option-label">{label}{selected}</span></div>'.format(
                indicator=indicator,
                label=escape(button.label),
                selected=selected_html,
            )
        )
    return f'<div class="interaction-options">{"".join(rendered)}</div>'


def _render_pdf_interaction_input(
    *,
    input_value: str,
    input_placeholder: str,
    compact: bool = False,
) -> str:
    value = input_value.strip()
    placeholder = input_placeholder.strip()
    content = escape(value or placeholder)
    value_class = (
        "interaction-input-value"
        if value
        else "interaction-input-value interaction-input-placeholder"
    )
    row_class = "interaction-input-row"
    if compact:
        row_class += " interaction-input-row--compact"
    return (
        f'<div class="{row_class}"><div class="interaction-response-label">{escape(PDF_EXPORT_INTERACTION_RESPONSE_LABEL)}</div><div class="interaction-input-shell">'
        f'<div class="{value_class}">{content}</div>'
        '<span class="interaction-send">↑</span></div></div>'
    )


def build_pdf_temp_dir(app: Flask) -> str:
    configured_root = str(app.config.get("PDF_EXPORT_TEMP_DIR", "") or "").strip()
    if configured_root:
        root = Path(configured_root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.mkdtemp(prefix=PDF_EXPORT_TEMP_DIR_PREFIX, dir=str(root))
    return tempfile.mkdtemp(prefix=PDF_EXPORT_TEMP_DIR_PREFIX)


def build_pdf_file_name(document: PdfExportDocument) -> str:
    base = (
        f"{PDF_EXPORT_BRAND_NAME}--{document.course_name}--{document.lesson_name}"
    ).strip("-")
    sanitized = sanitize_file_name(base) or f"{document.course_bid}-{document.lesson_bid}"
    return f"{sanitized}.pdf"


def sanitize_file_name(value: str) -> str:
    normalized = re.sub(r'[\\\\/:*?\"<>|]+', " ", str(value or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:120]


def generate_pdf_file(*, html: str, file_path: str) -> None:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - guarded by dependency install
        raise RuntimeError("weasyprint is required for lesson PDF export") from exc
    HTML(string=html).write_pdf(file_path)


def cleanup_expired_pdf_exports(app: Flask) -> dict[str, int]:
    ttl_seconds = int(
        app.config.get("PDF_EXPORT_TTL_SECONDS", PDF_EXPORT_DEFAULT_TTL_SECONDS)
    )
    configured_root = str(app.config.get("PDF_EXPORT_TEMP_DIR", "") or "").strip()
    if configured_root:
        scan_roots = [Path(configured_root).expanduser()]
    else:
        scan_roots = [Path(tempfile.gettempdir())]

    removed_dirs = 0
    removed_files = 0
    now = time.time()
    for root in scan_roots:
        if not root.exists():
            continue
        for candidate in root.glob(f"{PDF_EXPORT_TEMP_DIR_PREFIX}*"):
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if now - stat.st_mtime < ttl_seconds:
                continue
            if candidate.is_dir():
                for child in candidate.glob("**/*"):
                    if child.is_file():
                        try:
                            child.unlink()
                            removed_files += 1
                        except OSError:
                            app.logger.warning(
                                "Failed to remove expired pdf export file: %s",
                                child,
                                exc_info=True,
                            )
                for child_dir in sorted(
                    [p for p in candidate.glob("**/*") if p.is_dir()],
                    reverse=True,
                ):
                    try:
                        child_dir.rmdir()
                    except OSError:
                        pass
                try:
                    candidate.rmdir()
                    removed_dirs += 1
                except OSError:
                    app.logger.warning(
                        "Failed to remove expired pdf export directory: %s",
                        candidate,
                        exc_info=True,
                    )
            elif candidate.is_file():
                try:
                    candidate.unlink()
                    removed_files += 1
                except OSError:
                    app.logger.warning(
                        "Failed to remove expired pdf export file: %s",
                        candidate,
                        exc_info=True,
                    )
    return {
        "removed_dirs": removed_dirs,
        "removed_files": removed_files,
        "ttl_seconds": ttl_seconds,
    }
