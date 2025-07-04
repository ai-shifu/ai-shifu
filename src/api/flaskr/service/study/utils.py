import datetime
import json
import re
from flaskr.service.common.models import raise_error
from flask import Flask
from flaskr.util.uuid import generate_id
from ...service.lesson.const import (
    ASK_MODE_DEFAULT,
    ASK_MODE_DISABLE,
    LESSON_TYPE_BRANCH_HIDDEN,
    LESSON_TYPE_TRIAL,
    LESSON_TYPE_NORMAL,
    SCRIPT_TYPE_SYSTEM,
    UI_TYPE_BUTTON,
    UI_TYPE_EMPTY,
)
from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_COMPLETED,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_LOCKED,
    ATTEND_STATUS_NOT_STARTED,
    ATTEND_STATUS_RESET,
    get_attend_status_values,
)
from ...service.order.funs import (
    AICourseLessonAttendDTO,
)
from ...service.order.models import AICourseLessonAttend
from ...service.profile.funcs import get_user_profiles
from ...service.study.dtos import AILessonAttendDTO, ScriptDTO
from ...service.study.models import AICourseAttendAsssotion, AICourseLessonAttendScript
from ...dao import db
from ...service.order.funs import query_raw_buy_record
from ...service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.user.models import User
from flaskr.framework import extensible
from ...service.lesson.const import STATUS_PUBLISH, STATUS_DRAFT


def get_current_lesson(
    app: Flask, lesssons: list[AICourseLessonAttendDTO]
) -> AICourseLessonAttendDTO:
    return lesssons[0]


def generation_attend(
    app: Flask,
    attend: AICourseLessonAttendDTO,
    script_info: AILessonScript,
    with_ui_conf: bool = False,
) -> AICourseLessonAttendScript:
    attendScript = AICourseLessonAttendScript()
    attendScript.attend_id = attend.attend_id
    attendScript.user_id = attend.user_id
    attendScript.lesson_id = script_info.lesson_id
    attendScript.course_id = attend.course_id
    attendScript.script_id = script_info.script_id
    attendScript.script_ui_type = script_info.script_ui_type
    attendScript.log_id = generate_id(app)
    if with_ui_conf:
        attendScript.script_ui_conf = script_info.script_other_conf
    return attendScript


def check_phone_number(app, user_info: User, input):
    if not re.match(r"^1[3-9]\d{9}$", input):
        return False
    return True


# 得到一个课程的System Prompt


def get_lesson_system(app: Flask, lesson_id: str) -> str:
    status = [STATUS_PUBLISH, STATUS_DRAFT]
    # 缓存逻辑
    lesson_ids = [lesson_id]
    lesson = (
        AILesson.query.filter(
            AILesson.lesson_id == lesson_id, AILesson.status.in_(status)
        )
        .order_by(AILesson.id.desc())
        .first()
    )
    lesson_no = lesson.lesson_no
    parent_no = lesson_no
    if len(parent_no) > 2:
        parent_no = parent_no[:2]
    if parent_no != lesson_no:
        parent_lesson = (
            AILesson.query.filter(
                AILesson.lesson_no == parent_no,
                AILesson.course_id == lesson.course_id,
                AILesson.status.in_(status),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if parent_lesson:
            lesson_ids.append(parent_lesson.lesson_id)
    app.logger.info("lesson_ids:{}".format(lesson_ids))
    scripts = (
        AILessonScript.query.filter(
            AILessonScript.lesson_id.in_(lesson_ids),
            AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
            AILessonScript.status.in_(status),
        )
        .order_by(AILessonScript.id.desc())
        .all()
    )
    app.logger.info("scripts:{}".format(scripts))
    if len(scripts) > 0:
        for script in scripts:
            if script.lesson_id == lesson_id:
                return script.script_prompt
        return scripts[0].script_prompt
    return None


def fmt(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    else:
        return o.__json__()


def get_profile_array(profile: str) -> list:
    return re.findall(r"\[(.*?)\]", profile)


def get_lesson_and_attend_info(
    app: Flask, parent_no, course_id, user_id, preview_mode: bool = False
):
    status = [STATUS_PUBLISH]
    if preview_mode:
        status.append(STATUS_DRAFT)
    lessons = (
        AILesson.query.filter(
            AILesson.lesson_no.like(parent_no + "%"),
            AILesson.course_id == course_id,
            AILesson.lesson_type != LESSON_TYPE_BRANCH_HIDDEN,
            AILesson.status.in_(status),
        )
        .order_by(AILesson.id.desc())
        .all()
    )
    if len(lessons) == 0:
        return []
    app.logger.info(
        "lessons:{}".format(
            ",".join("'" + lesson.lesson_no + "'" for lesson in lessons)
        )
    )
    attend_infos = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.lesson_id.in_([lesson.lesson_id for lesson in lessons]),
        AICourseLessonAttend.user_id == user_id,
        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
    ).all()

    if len(attend_infos) != len(lessons):
        filtered_lessons = []
        if preview_mode:
            filtered_lessons = [lesson for lesson in lessons if lesson.status in [1, 2]]
        else:
            filtered_lessons = [lesson for lesson in lessons if lesson.status == 1]

        if not filtered_lessons:
            return []

        lesson_type = filtered_lessons[0].lesson_type
        add_attend = False
        if lesson_type == LESSON_TYPE_TRIAL:
            add_attend = True
        elif lesson_type == LESSON_TYPE_NORMAL:
            raw_order = query_raw_buy_record(app, user_id, course_id)
            if raw_order and raw_order.status == BUY_STATUS_SUCCESS:
                add_attend = True
            else:
                raise_error("COURSE.COURSE_NOT_PURCHASED")
        if add_attend:
            app.logger.info("add attend to fix attend info")
            for lesson in filtered_lessons:
                attends = [
                    attend
                    for attend in attend_infos
                    if attend.lesson_id == lesson.lesson_id
                ]
                if len(attends) == 0:
                    app.logger.info("add attend to lesson:{}".format(lesson.lesson_id))
                    attend = AICourseLessonAttend()
                    attend.attend_id = generate_id(app)
                    attend.lesson_id = lesson.lesson_id
                    attend.course_id = course_id
                    attend.user_id = user_id
                    attend.status = ATTEND_STATUS_LOCKED
                    attend.lesson_no = lesson.lesson_no
                    db.session.add(attend)
                    attend_infos.append(attend)
            db.session.flush()

    attend_lesson_infos = [
        {
            "attend": attend,
            "lesson": [
                lesson for lesson in lessons if lesson.lesson_id == attend.lesson_id
            ][0],
        }
        for attend in attend_infos
    ]
    app.logger.info("attend_lesson_infos length:{}".format(len(attend_lesson_infos)))
    attend_lesson_infos = sorted(
        attend_lesson_infos,
        key=lambda x: (len(x["lesson"].lesson_no), x["lesson"].lesson_no),
    )
    app.logger.info(
        "attends:{}".format(
            ",".join("'" + a["lesson"].lesson_no + "'" for a in attend_lesson_infos)
        )
    )
    return attend_lesson_infos


# 从文本中提取json对象
def extract_json(app: Flask, text: str):
    stack = []
    start = None
    for i, char in enumerate(text):
        if char == "{":
            if not stack:
                start = i
            stack.append(char)
        elif char == "}":
            if stack:
                stack.pop()
                if not stack:
                    json_str = text[start : i + 1]  # noqa
                    try:
                        json_obj = json.loads(json_str)
                        return json_obj
                    except json.JSONDecodeError:
                        pass
    return {}


def extract_variables(template: str) -> list:
    # Match all {xxx} or {{xxx}} in the template
    pattern = r"\{{1,2}([^{}]+)\}{1,2}"
    matches = re.findall(pattern, template)
    # Only keep valid variable names (letters, digits, underscore, hyphen), no dots, commas, colons, quotes, or spaces
    variables = [
        m.strip()
        for m in matches
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", m.strip())
    ]
    return list(set(variables))


def safe_format_template(template: str, variables: dict) -> str:
    # Replace {xxx} or {{xxx}} with values from variables dict, keep original if not found
    pattern = re.compile(r"(\{{1,2})([^{}]+)(\}{1,2})")

    def replacer(match):
        left, var, right = match.groups()
        var_name = var.strip()
        # Only process variable names with letters, digits, underscore, hyphen
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", var_name):
            if var_name in variables:
                return str(variables[var_name])
        # Otherwise, keep the original
        return match.group(0)

    return pattern.sub(replacer, template)


def get_fmt_prompt(
    app: Flask,
    user_id: str,
    course_id: str,
    profile_tmplate: str,
    input: str = None,
    profile_array_str: str = None,
) -> str:
    app.logger.info("raw prompt:" + profile_tmplate)
    propmpt_keys = []
    profiles = {}

    profiles = get_user_profiles(app, user_id, course_id)
    propmpt_keys = list(profiles.keys())
    if input:
        profiles["sys_user_input"] = input
        propmpt_keys.append("sys_user_input")
    app.logger.info(propmpt_keys)
    app.logger.info(profiles)
    keys = extract_variables(profile_tmplate)
    fmt_keys = {}
    for key in keys:
        if key in profiles:
            fmt_keys[key] = profiles[key]
        else:
            app.logger.info("key not found:" + key + " ,user_id:" + user_id)
    app.logger.info(fmt_keys)
    if not keys:
        prompt = input if not profile_tmplate else profile_tmplate
    else:
        prompt = safe_format_template(profile_tmplate, fmt_keys)
    app.logger.info("fomat input:{}".format(prompt))
    return prompt


def get_script(app: Flask, attend_id: str, next: int = 0, preview_mode: bool = False):
    status = [STATUS_PUBLISH]
    if preview_mode:
        status.append(STATUS_DRAFT)
    is_first = False
    attend_info = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.attend_id == attend_id
    ).first()
    attend_infos = []
    attend_status_values = get_attend_status_values()
    app.logger.info(
        "get next script,current:{},next:{}".format(attend_info.script_index, next)
    )
    if attend_info.status == ATTEND_STATUS_NOT_STARTED or attend_info.script_index <= 0:
        attend_info.status = ATTEND_STATUS_IN_PROGRESS
        attend_info.script_index = 1
        # 检查是否是第一节课
        lesson = (
            AILesson.query.filter(
                AILesson.lesson_id == attend_info.lesson_id,
                AILesson.status.in_(status),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        attend_infos.append(
            AILessonAttendDTO(
                lesson.lesson_no,
                lesson.lesson_name,
                lesson.lesson_id,
                attend_status_values[ATTEND_STATUS_IN_PROGRESS],
                ATTEND_STATUS_IN_PROGRESS,
                lesson.lesson_type,
            )
        )
        app.logger.info(lesson.lesson_no)
        app.logger.info(lesson.lesson_no[-2:])
        if len(lesson.lesson_no) >= 2 and lesson.lesson_no[-2:] == "01":
            # 第一节课
            app.logger.info("first lesson")
            parent_lesson = (
                AILesson.query.filter(
                    AILesson.lesson_no == lesson.lesson_no[:-2],
                    AILesson.course_id == lesson.course_id,
                    AILesson.status.in_(status),
                )
                .order_by(AILesson.id.desc())
                .first()
            )
            parent_attend = (
                AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.lesson_id == parent_lesson.lesson_id,
                    AICourseLessonAttend.user_id == attend_info.user_id,
                    AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                )
                .order_by(AICourseLessonAttend.id.desc())
                .first()
            )
            is_first = True
            if (
                parent_attend is not None
                and parent_attend.status == ATTEND_STATUS_NOT_STARTED
            ):
                parent_attend.status = ATTEND_STATUS_IN_PROGRESS
                attend_infos.append(
                    AILessonAttendDTO(
                        parent_lesson.lesson_no,
                        parent_lesson.lesson_name,
                        parent_lesson.lesson_id,
                        attend_status_values[ATTEND_STATUS_IN_PROGRESS],
                        ATTEND_STATUS_IN_PROGRESS,
                        parent_lesson.lesson_type,
                    )
                )

    elif attend_info.status == ATTEND_STATUS_BRANCH:
        # 分支课程
        app.logger.info("branch")
        current = attend_info
        assoation = AICourseAttendAsssotion.query.filter(
            AICourseAttendAsssotion.from_attend_id == current.attend_id
        ).first()
        if assoation:
            app.logger.info("found assoation")
            current = AICourseLessonAttend.query.filter(
                AICourseLessonAttend.attend_id == assoation.to_attend_id
            ).first()
        while current.status == ATTEND_STATUS_BRANCH:
            # 分支课程
            assoation = AICourseAttendAsssotion.query.filter(
                AICourseAttendAsssotion.from_attend_id == current.attend_id
            ).first()
            if assoation:
                current = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.attend_id == assoation.to_attend_id
                ).first()
        app.logger.info("to get branch script")
        db.session.flush()
        script_info, attend_infos, is_first = get_script(
            app, current.attend_id, next, preview_mode
        )
        if script_info:
            return script_info, [], is_first
        else:
            current.status = ATTEND_STATUS_COMPLETED
            attend_info.status = ATTEND_STATUS_IN_PROGRESS
            db.session.flush()
            return get_script(app, attend_id, next, preview_mode)
    elif next > 0:
        attend_info.script_index = attend_info.script_index + next

    subquery = []
    script_info = None
    if preview_mode:
        subquery = (
            db.session.query(db.func.max(AILessonScript.id))
            .filter(
                AILessonScript.lesson_id == (attend_info.lesson_id),
            )
            .group_by(AILessonScript.script_id)
        )
        script_info = (
            AILessonScript.query.filter(
                AILessonScript.id.in_(subquery),
                AILessonScript.lesson_id == attend_info.lesson_id,
                AILessonScript.status.in_(status),
                AILessonScript.script_index == attend_info.script_index,
                AILessonScript.script_type != SCRIPT_TYPE_SYSTEM,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
    else:
        script_info = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == attend_info.lesson_id,
                AILessonScript.status.in_(status),
                AILessonScript.script_index == attend_info.script_index,
                AILessonScript.script_type != SCRIPT_TYPE_SYSTEM,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
    if not script_info:
        app.logger.info("no script found")
        app.logger.info(attend_info.lesson_id)
        if attend_info.status == ATTEND_STATUS_IN_PROGRESS:
            attend_info.status = ATTEND_STATUS_COMPLETED
            lesson = (
                AILesson.query.filter(
                    AILesson.lesson_id == attend_info.lesson_id,
                    AILesson.status.in_(status),
                )
                .order_by(AILesson.id.desc())
                .first()
            )
            attend_infos.append(
                AILessonAttendDTO(
                    lesson.lesson_no,
                    lesson.lesson_name,
                    lesson.lesson_id,
                    attend_status_values[ATTEND_STATUS_COMPLETED],
                    ATTEND_STATUS_COMPLETED,
                    lesson.lesson_type,
                )
            )
    db.session.flush()
    return script_info, attend_infos, is_first


def get_script_by_id(
    app: Flask, script_id: str, preview_mode: bool = False
) -> AILessonScript:
    status = [STATUS_PUBLISH]
    if preview_mode:
        status.append(STATUS_DRAFT)
    return (
        AILessonScript.query.filter(
            AILessonScript.script_id == script_id,
            AILessonScript.status.in_(status),
        )
        .order_by(AILessonScript.id.desc())
        .first()
    )


def make_script_dto(
    script_type, script_content, script_id, lesson_id=None, log_id=None
) -> str:
    return (
        "data: "
        + json.dumps(
            ScriptDTO(script_type, script_content, lesson_id, script_id, log_id),
            default=fmt,
        )
        + "\n\n".encode("utf-8").decode("utf-8")
    )


def make_script_dto_to_stream(dto: ScriptDTO) -> str:
    return (
        "data: " + json.dumps(dto, default=fmt) + "\n\n".encode("utf-8").decode("utf-8")
    )


@extensible
def update_lesson_status(app: Flask, attend_id: str, preview_mode: bool = False):
    status = [STATUS_PUBLISH]
    if preview_mode:
        status.append(STATUS_DRAFT)
    attend_status_values = get_attend_status_values()
    res = []
    attend_info = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.attend_id == attend_id
    ).first()
    lesson = (
        AILesson.query.filter(
            AILesson.lesson_id == attend_info.lesson_id,
            AILesson.status.in_(status),
        )
        .order_by(AILesson.id.desc())
        .first()
    )
    lesson_no = lesson.lesson_no
    parent_no = lesson_no
    attend_info.status = ATTEND_STATUS_COMPLETED
    res.append(
        AILessonAttendDTO(
            lesson_no,
            lesson.lesson_name,
            lesson.lesson_id,
            attend_status_values[ATTEND_STATUS_COMPLETED],
            ATTEND_STATUS_COMPLETED,
            lesson.lesson_type,
        )
    )
    if len(parent_no) > 2:
        parent_no = parent_no[:2]
    app.logger.info("parent_no:" + parent_no)
    attend_lesson_infos = get_lesson_and_attend_info(
        app, parent_no, lesson.course_id, attend_info.user_id, preview_mode
    )
    if attend_lesson_infos[-1]["attend"].attend_id == attend_id:
        attend_status_values = get_attend_status_values()
        # 最后一个已经完课
        # 整体章节完课
        if attend_lesson_infos[0]["attend"].status == ATTEND_STATUS_IN_PROGRESS:
            attend_lesson_infos[0]["attend"].status = ATTEND_STATUS_COMPLETED
            res.append(
                AILessonAttendDTO(
                    attend_lesson_infos[0]["lesson"].lesson_no,
                    attend_lesson_infos[0]["lesson"].lesson_name,
                    attend_lesson_infos[0]["lesson"].lesson_id,
                    attend_status_values[ATTEND_STATUS_COMPLETED],
                    ATTEND_STATUS_COMPLETED,
                    attend_lesson_infos[0]["lesson"].lesson_type,
                )
            )
        # 找到下一章节进行解锁
        next_no = str(int(parent_no) + 1).zfill(2)
        next_lessons = get_lesson_and_attend_info(
            app, next_no, lesson.course_id, attend_info.user_id, preview_mode
        )

        app.logger.info("next_no:" + next_no)
        if len(next_lessons) > 0:
            # 解锁
            app.logger.info(
                "next lesson: {} ".format(
                    ",".join(
                        [
                            (nl["lesson"].lesson_no + ":" + str(nl["attend"].status))
                            for nl in next_lessons
                        ]
                    )
                )
            )
            for next_lesson_attend in next_lessons:
                if next_lesson_attend["lesson"].lesson_no == next_no and (
                    next_lesson_attend["attend"].status == ATTEND_STATUS_LOCKED
                    or next_lesson_attend["attend"].status == ATTEND_STATUS_NOT_STARTED
                    or next_lesson_attend["attend"].status == ATTEND_STATUS_IN_PROGRESS
                ):
                    app.logger.info("unlock next lesson")
                    next_lesson_attend["attend"].status = ATTEND_STATUS_NOT_STARTED
                    res.append(
                        AILessonAttendDTO(
                            next_lesson_attend["lesson"].lesson_no,
                            next_lesson_attend["lesson"].lesson_name,
                            next_lesson_attend["lesson"].lesson_id,
                            attend_status_values[ATTEND_STATUS_NOT_STARTED],
                            ATTEND_STATUS_NOT_STARTED,
                            next_lesson_attend["lesson"].lesson_type,
                        )
                    )
                if next_lesson_attend["lesson"].lesson_no == next_no + "01" and (
                    next_lesson_attend["attend"].status == ATTEND_STATUS_LOCKED
                    or next_lesson_attend["attend"].status == ATTEND_STATUS_NOT_STARTED
                    or next_lesson_attend["attend"].status == ATTEND_STATUS_IN_PROGRESS
                ):
                    app.logger.info("unlock next lesson")
                    next_lesson_attend["attend"].status = ATTEND_STATUS_NOT_STARTED
                    res.append(
                        AILessonAttendDTO(
                            next_lesson_attend["lesson"].lesson_no,
                            next_lesson_attend["lesson"].lesson_name,
                            next_lesson_attend["lesson"].lesson_id,
                            attend_status_values[ATTEND_STATUS_NOT_STARTED],
                            ATTEND_STATUS_NOT_STARTED,
                            next_lesson_attend["lesson"].lesson_type,
                        )
                    )
        else:
            app.logger.info("no next lesson")
    app.logger.info("current res lenth:{}".format(len(res)))
    for i in range(len(attend_lesson_infos)):
        if (
            i > 0
            and attend_lesson_infos[i - 1]["attend"].attend_id == attend_id
            and attend_lesson_infos[i]["attend"].status == ATTEND_STATUS_LOCKED
        ):
            # 更新下一节
            attend_lesson_infos[i]["attend"].status = ATTEND_STATUS_NOT_STARTED
            res.append(
                AILessonAttendDTO(
                    attend_lesson_infos[i]["lesson"].lesson_no,
                    attend_lesson_infos[i]["lesson"].lesson_name,
                    attend_lesson_infos[i]["lesson"].lesson_id,
                    attend_status_values[ATTEND_STATUS_NOT_STARTED],
                    ATTEND_STATUS_NOT_STARTED,
                    attend_lesson_infos[i]["lesson"].lesson_type,
                )
            )
    return res


class FollowUpInfo:

    ask_model: str
    ask_prompt: str
    ask_history_count: int
    ask_limit_count: int
    model_args: dict
    ask_mode: int

    def __init__(
        self,
        ask_model,
        ask_prompt,
        ask_history_count,
        ask_limit_count,
        model_args,
        ask_mode,
    ):
        self.ask_model = ask_model
        self.ask_prompt = ask_prompt
        self.ask_history_count = ask_history_count
        self.ask_limit_count = ask_limit_count
        self.model_args = model_args
        self.ask_mode = ask_mode

    def __json__(self):
        return {
            "ask_model": self.ask_model,
            "ask_prompt": self.ask_prompt,
            "ask_history_count": self.ask_history_count,
            "ask_limit_count": self.ask_limit_count,
            "model_args": self.model_args,
            "ask_mode": self.ask_mode,
        }


def get_follow_up_info(app: Flask, script_info: AILessonScript) -> FollowUpInfo:
    if script_info.ask_mode != ASK_MODE_DEFAULT:
        app.logger.info(f"script_info.ask_mode: {script_info.ask_mode}")
        return FollowUpInfo(
            script_info.ask_model,
            script_info.ask_prompt,
            script_info.ask_with_history,
            script_info.ask_count_limit,
            {},
            script_info.ask_mode,
        )
    # todo add cache info
    ai_lesson = (
        AILesson.query.filter(
            AILesson.lesson_id == script_info.lesson_id,
            AILesson.status == 1,
        )
        .order_by(AILesson.id.desc())
        .first()
    )

    if not ai_lesson:
        return FollowUpInfo(
            ask_model="",
            ask_prompt="",
            ask_history_count=0,
            ask_limit_count=0,
            model_args={},
            ask_mode=ASK_MODE_DISABLE,
        )
    if ai_lesson.ask_mode != ASK_MODE_DEFAULT:
        ask_model = ai_lesson.ask_model
        ask_prompt = ai_lesson.ask_prompt
        ask_history_count = ai_lesson.ask_with_history
        ask_limit_count = ai_lesson.ask_count_limit
        model_args = {}
        return FollowUpInfo(
            ask_model,
            ask_prompt,
            ask_history_count,
            ask_limit_count,
            model_args,
            ai_lesson.ask_mode,
        )
    parent_lesson = (
        AILesson.query.filter(
            AILesson.course_id == ai_lesson.course_id,
            AILesson.lesson_no == ai_lesson.lesson_no[:2],
            AILesson.status == 1,
        )
        .order_by(AILesson.id.desc())
        .first()
    )
    if parent_lesson.ask_mode != ASK_MODE_DEFAULT:
        app.logger.info(f"parent_lesson.ask_mode: {parent_lesson.ask_mode}")
        ask_model = parent_lesson.ask_model
        ask_prompt = parent_lesson.ask_prompt
        ask_history_count = parent_lesson.ask_with_history
        ask_limit_count = parent_lesson.ask_count_limit
        model_args = {}
        return FollowUpInfo(
            ask_model,
            ask_prompt,
            ask_history_count,
            ask_limit_count,
            model_args,
            parent_lesson.ask_mode,
        )

    ai_course = (
        AICourse.query.filter(
            AICourse.course_id == ai_lesson.course_id,
            AICourse.status == 1,
        )
        .order_by(AICourse.id.desc())
        .first()
    )
    ask_model = ai_course.ask_model
    ask_prompt = ai_course.ask_prompt
    ask_history_count = ai_course.ask_with_history
    ask_limit_count = ai_course.ask_count_limit
    model_args = {}
    return FollowUpInfo(
        ask_model,
        ask_prompt,
        ask_history_count,
        ask_limit_count,
        model_args,
        ai_course.ask_mode,
    )


class ModelSetting:

    model_name: str
    model_args: dict

    def __init__(self, model_name: str, model_args: dict):
        self.model_name = model_name
        self.model_args = model_args

    def __json__(self):
        return {"model_name": self.model_name, "model_args": self.model_args}


def get_model_setting(
    app: Flask, script_info: AILessonScript, status: list[int] = None
) -> ModelSetting:
    if status is None:
        status = [STATUS_PUBLISH, STATUS_DRAFT]
    if script_info.script_model and script_info.script_model.strip():
        return ModelSetting(
            script_info.script_model, {"temperature": script_info.script_temperature}
        )
    ai_lesson = (
        AILesson.query.filter(
            AILesson.lesson_id == script_info.lesson_id,
            AILesson.status.in_(status),
        )
        .order_by(AILesson.id.desc())
        .first()
    )
    if (
        ai_lesson
        and ai_lesson.lesson_default_model
        and ai_lesson.lesson_default_model.strip()
    ):
        return ModelSetting(
            ai_lesson.lesson_default_model,
            {"temperature": ai_lesson.lesson_default_temperature},
        )
    ai_course = (
        AICourse.query.filter(
            AICourse.course_id == ai_lesson.course_id,
            AICourse.status.in_(status),
        )
        .order_by(AICourse.id.desc())
        .first()
    )
    if (
        ai_course
        and ai_course.course_default_model
        and ai_course.course_default_model.strip()
    ):
        return ModelSetting(
            ai_course.course_default_model,
            {"temperature": ai_course.course_default_temperature},
        )
    default_model = app.config.get("DEFAULT_LLM_MODEL", "")
    if not default_model or default_model == "":
        raise_error("LLM.NO_DEFAULT_LLM")
    return ModelSetting(
        app.config.get("DEFAULT_LLM_MODEL"),
        {"temperature": float(app.config.get("DEFAULT_LLM_TEMPERATURE"))},
    )


@extensible
def check_script_is_last_script(
    app: Flask,
    script_info: AILessonScript,
    lesson_info: AILesson,
    preview_mode: bool = False,
) -> bool:
    status = [STATUS_PUBLISH]
    if preview_mode:
        status.append(STATUS_DRAFT)
    parent_lesson_no = lesson_info.lesson_no
    if len(parent_lesson_no) > 2:
        parent_lesson_no = parent_lesson_no[:2]
    last_lesson = (
        AILesson.query.filter(
            AILesson.lesson_no.like(parent_lesson_no + "__"),
            AILesson.course_id == lesson_info.course_id,
            AILesson.status.in_(status),
        )
        .order_by(AILesson.lesson_no.desc(), AILesson.id.desc())
        .first()
    )
    if last_lesson.lesson_id == script_info.lesson_id:
        subquery = []
        last_script = None
        if preview_mode:
            subquery = (
                db.session.query(db.func.max(AILessonScript.id))
                .filter(
                    AILessonScript.lesson_id == last_lesson.lesson_id,
                )
                .group_by(AILessonScript.script_id)
            )
            last_script = (
                AILessonScript.query.filter(
                    AILessonScript.id.in_(subquery),
                    AILessonScript.lesson_id == last_lesson.lesson_id,
                    AILessonScript.status.in_(status),
                )
                .order_by(AILessonScript.script_index.desc())
                .first()
            )
        else:
            last_script = (
                AILessonScript.query.filter(
                    AILessonScript.lesson_id == last_lesson.lesson_id,
                    AILessonScript.status.in_(status),
                )
                .order_by(AILessonScript.script_index.desc())
                .first()
            )
        if (
            last_script.script_id == script_info.script_id
            and last_script.script_ui_type in [UI_TYPE_BUTTON, UI_TYPE_EMPTY]
        ):
            return True
    return False
