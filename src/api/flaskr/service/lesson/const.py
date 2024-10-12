SCRIPT_TYPE_FIX = 101
SCRIPT_TYPE_PORMPT = 102
SCRIPT_TYPE_SYSTEM = 103
SCRIPT_TYPES = {
    "固定剧本": SCRIPT_TYPE_FIX,
    "Prompt": SCRIPT_TYPE_PORMPT,
    "系统角色": SCRIPT_TYPE_SYSTEM,
}

SCRIPT_TYPE_VALUES = {
    SCRIPT_TYPE_FIX: "固定剧本",
    SCRIPT_TYPE_PORMPT: "Prompt",
    SCRIPT_TYPE_SYSTEM: "系统角色",
}

CONTENT_TYPE_TEXT = 201
CONTENT_TYPE_IMAGE = 202
CONTENT_TYPES = {"文本": CONTENT_TYPE_TEXT, "图片": CONTENT_TYPE_IMAGE}

UI_TYPE_BUTTON = 301
UI_TYPE_INPUT = 302
UI_TYPE_CONTINUED = 303
UI_TYPE_TO_PAY = 304
UI_TYPE_SELECTION = 305
UI_TYPE_PHONE = 306
UI_TYPE_CHECKCODE = 307
UI_TYPE_LOGIN = 308
UI_TYPE_BRANCH = 309

UI_TYPES = {
    "显示 按钮": UI_TYPE_BUTTON,
    "显示 输入框": UI_TYPE_INPUT,
    "显示 付款码": UI_TYPE_TO_PAY,
    "显示 按钮组": UI_TYPE_SELECTION,
    "输入 手机号": UI_TYPE_PHONE,
    "输入 验证码": UI_TYPE_CHECKCODE,
    "弹出 登录注册框": UI_TYPE_LOGIN,
    "显示 登录注册框": UI_TYPE_LOGIN,
    "无": UI_TYPE_CONTINUED,
    "跳转按钮": UI_TYPE_BRANCH,
}


UI_TYPE_VALUES = {
    UI_TYPE_BUTTON: "显示 按钮",
    UI_TYPE_INPUT: "显示 输入框",
    UI_TYPE_TO_PAY: "显示 付款码",
    UI_TYPE_SELECTION: "显示 按钮组",
    UI_TYPE_PHONE: "输入 手机号",
    UI_TYPE_CHECKCODE: "输入 验证码",
    UI_TYPE_LOGIN: "弹出 登录注册框",
    UI_TYPE_CONTINUED: "无",
    UI_TYPE_BRANCH: "跳转按钮",
}


LESSON_TYPE_TRIAL = 401
LESSON_TYPE_NORMAL = 402
LESSON_TYPE_EXTEND = 403
LESSON_TYPE_BRANCH = 404
LESSON_TYPE_BRANCH_HIDDEN = 405
LESSON_TYPES = {
    "试用课": LESSON_TYPE_TRIAL,
    "正式课": LESSON_TYPE_NORMAL,
    "延展课": LESSON_TYPE_EXTEND,
    "分支课": LESSON_TYPE_BRANCH,
    "隐藏分支课": LESSON_TYPE_BRANCH_HIDDEN,
}

LESSON_STATUS = {1: "有效", 0: "无效"}

SCRIPT_STATUS = {1: "有效", 0: "无效"}
LESSON_TYPE_VALUES = {
    LESSON_TYPE_TRIAL: "试用课",
    LESSON_TYPE_NORMAL: "正式课",
    LESSON_TYPE_EXTEND: "延展课",
    LESSON_TYPE_BRANCH: "分支课",
    LESSON_TYPE_BRANCH_HIDDEN: "隐藏分支课",
}

ASK_MODE_DEFAULT = 5101
ASK_MODE_DISABLE = 5102
ASK_MODE_ENABLE = 5103

ASK_MODES = {
    "默认": ASK_MODE_DEFAULT,
    "禁用": ASK_MODE_DISABLE,
    "启用": ASK_MODE_ENABLE,
}
