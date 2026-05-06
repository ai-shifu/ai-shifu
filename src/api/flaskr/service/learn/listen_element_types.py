from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.service.learn.const import ROLE_STUDENT, ROLE_UI
from flaskr.service.learn.learn_dtos import ElementChangeType, ElementType
from flaskr.util.uuid import generate_id

ELEMENT_TYPE_CODES = {
    ElementType.HTML: 201,
    ElementType.SVG: 202,
    ElementType.DIFF: 203,
    ElementType.IMG: 204,
    ElementType.INTERACTION: 205,
    ElementType.ASK: 206,
    ElementType.ANSWER: 214,
    ElementType.TABLES: 207,
    ElementType.CODE: 208,
    ElementType.LATEX: 209,
    ElementType.MD_IMG: 210,
    ElementType.MERMAID: 211,
    ElementType.TITLE: 212,
    ElementType.TEXT: 213,
    ElementType._SANDBOX: 102,
    ElementType._PICTURE: 103,
    ElementType._VIDEO: 104,
}

VISUAL_KIND_ELEMENT_TYPE_ALIASES = {
    "video": ElementType.HTML,
    "iframe": ElementType.HTML,
    "sandbox": ElementType.HTML,
    "html_table": ElementType.HTML,
    "md_table": ElementType.TABLES,
    "fence": ElementType.CODE,
    "md_img": ElementType.MD_IMG,
}

LEGACY_ELEMENT_TYPE_MAP = {
    ElementType._SANDBOX: ElementType.HTML,
    ElementType._PICTURE: ElementType.IMG,
    ElementType._VIDEO: ElementType.HTML,
}


def _normalize_bool(raw: Any) -> bool:
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return bool(raw)


def _role_value_to_name(role_value: Any) -> str:
    if role_value == ROLE_STUDENT:
        return "student"
    if role_value == ROLE_UI:
        return "ui"
    return "teacher"


def _element_type_for_visual_kind(visual_kind: str) -> ElementType:
    normalized = (visual_kind or "").strip().lower()
    alias = VISUAL_KIND_ELEMENT_TYPE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    try:
        return ElementType(normalized)
    except ValueError:
        return ElementType.TEXT


def _element_type_code(element_type: ElementType) -> int:
    return ELEMENT_TYPE_CODES[element_type]


def _default_is_marker(element_type: ElementType) -> bool:
    return element_type not in {ElementType.TEXT, ElementType.ASK, ElementType.ANSWER}


def _default_is_renderable(element_type: ElementType) -> bool:
    return element_type not in {
        ElementType.TEXT,
        ElementType.ASK,
        ElementType.ANSWER,
        ElementType.INTERACTION,
    }


def _default_is_speakable(element_type: ElementType, content_text: str = "") -> bool:
    return element_type == ElementType.TEXT and bool(content_text)


def _normalized_is_speakable(
    element_type: ElementType,
    content_text: str = "",
    *,
    stored_is_speakable: bool = False,
) -> bool:
    if element_type != ElementType.TEXT:
        return False
    return bool(
        stored_is_speakable or _default_is_speakable(element_type, content_text)
    )


def _new_element_bid(app: Flask) -> str:
    return generate_id(app)


def _visual_type_for_element(element_type: ElementType) -> str:
    if element_type == ElementType.TABLES:
        return "md_table"
    if element_type == ElementType.CODE:
        return "fence"
    if element_type == ElementType.MD_IMG:
        return "md_img"
    if element_type in {
        ElementType.HTML,
        ElementType.SVG,
        ElementType.DIFF,
        ElementType.IMG,
        ElementType.LATEX,
        ElementType.MERMAID,
    }:
        return element_type.value
    return ""


def _change_type_for_element(element_type: ElementType) -> ElementChangeType:
    if element_type == ElementType.DIFF:
        return ElementChangeType.DIFF
    return ElementChangeType.RENDER
