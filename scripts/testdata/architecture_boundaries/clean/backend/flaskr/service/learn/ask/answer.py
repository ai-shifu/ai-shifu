"""Exercise a follow-up module that depends only on the element layer and DTOs."""

from flaskr.service.learn.elements.queries import load_rows
from flaskr.service.learn.learn_dtos import RunStatusDTO


def answer() -> tuple[object, object]:
    return load_rows, RunStatusDTO
