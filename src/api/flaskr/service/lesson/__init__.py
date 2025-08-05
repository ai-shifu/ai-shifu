from .funcs import update_lesson_info, get_lessons  # noqa: F401
from .const import SCRIPT_TYPES, CONTENT_TYPES, LESSON_TYPES  # noqa: F401
from .models import *  # noqa: F403 F401
from ..common.dicts import register_dict

register_dict("script_types", "剧本类型", SCRIPT_TYPES)
register_dict("content_types", "内容类型", CONTENT_TYPES)
register_dict("lesston_types", "课程类型", LESSON_TYPES)
