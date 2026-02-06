from flaskr.service.common.dicts import register_dict

from .consts import (  # noqa: F401
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_DICT,
    BILL_USAGE_SCENE_NON_BILLABLE,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_DICT,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
    normalize_usage_scene,
    normalize_usage_type,
)
from .models import BillUsageRecord  # noqa: F401
from .recorder import UsageContext, record_llm_usage, record_tts_usage  # noqa: F401

register_dict("bill_usage_type", "Bill usage type", BILL_USAGE_TYPE_DICT)
register_dict("bill_usage_scene", "Bill usage scene", BILL_USAGE_SCENE_DICT)
