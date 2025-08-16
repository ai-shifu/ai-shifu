from .consts import *  # noqa
from .funs import *  # noqa
from ..common.dicts import register_dict


register_dict("order_status", "订单状态", ORDER_STATUS_TYPES)  # noqa
register_dict("learn_status", "学习状态", LEARN_STATUS_TYPES)  # noqa
