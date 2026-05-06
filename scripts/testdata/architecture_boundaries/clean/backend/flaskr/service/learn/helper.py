from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.dtos import ExampleDto
from flaskr.service.order.api import list_operator_orders


def build_payload() -> tuple[object, object, object]:
    return raise_param_error, ExampleDto, list_operator_orders
