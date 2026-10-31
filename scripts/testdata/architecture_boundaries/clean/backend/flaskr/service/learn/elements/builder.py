"""Exercise an element module that depends only on learn DTOs and models."""

from flaskr.service.learn.learn_dtos import ElementDTO
from flaskr.service.learn.models import LearnGeneratedElement


def build_elements() -> tuple[object, object]:
    return ElementDTO, LearnGeneratedElement
