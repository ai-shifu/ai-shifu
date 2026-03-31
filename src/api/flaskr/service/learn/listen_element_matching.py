from __future__ import annotations

from typing import Iterable

from flaskr.service.learn.learn_dtos import ElementDTO, ElementType


def get_speakable_text_elements(
    elements: Iterable[ElementDTO] | None,
) -> list[ElementDTO]:
    return [
        element
        for element in (elements or [])
        if element.element_type == ElementType.TEXT
        and (element.content_text or "").strip()
    ]
