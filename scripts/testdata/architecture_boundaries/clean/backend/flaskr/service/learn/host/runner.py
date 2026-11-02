"""Exercise a host module that depends only on the element layer and DTOs."""

from flaskr.service.learn.elements.run_adapter import ListenElementRunAdapter
from flaskr.service.learn.learn_dtos import RunStatusDTO


def run_request() -> tuple[object, object]:
    return ListenElementRunAdapter, RunStatusDTO
