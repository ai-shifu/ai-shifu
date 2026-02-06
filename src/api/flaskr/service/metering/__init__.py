from flaskr.service.common.dicts import register_dict

from .consts import BILL_USAGE_SCENE_DICT, BILL_USAGE_TYPE_DICT
from .models import BillUsageRecord  # noqa: F401
from .recorder import UsageContext, record_llm_usage, record_tts_usage  # noqa: F401

register_dict("bill_usage_type", "Bill usage type", BILL_USAGE_TYPE_DICT)  # noqa
register_dict("bill_usage_scene", "Bill usage scene", BILL_USAGE_SCENE_DICT)  # noqa
