from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.dtos import ExampleDto


def build_payload() -> tuple[object, object]:
    return raise_param_error, ExampleDto
