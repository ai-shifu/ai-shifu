from __future__ import annotations

from typing import Iterable

from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
from flaskr.service.learn.listen_element_types import _default_is_speakable


def get_speakable_text_elements(
    elements: Iterable[ElementDTO] | None,
) -> list[ElementDTO]:
    return [
        element
        for element in (elements or [])
        if element.element_type == ElementType.TEXT
        and element.is_speakable
        and (element.content_text or "").strip()
        and _default_is_speakable(ElementType.TEXT, element.content_text or "")
    ]
