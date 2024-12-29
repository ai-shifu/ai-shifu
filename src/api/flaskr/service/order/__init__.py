from .consts import *  # noqa
from .funs import *  # noqa
from ..common.dicts import register_dict


register_dict("order_status", "订单状态", BUY_STATUS_TYPES)  # noqa
register_dict("attend_status", "到课状态", ATTEND_STATUS_TYPES)  # noqa
