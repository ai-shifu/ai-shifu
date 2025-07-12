import time
import json
from trace import Trace
from flask import Flask
from flaskr.api.llm import invoke_llm
from flaskr.service.study.input_funcs import BreakException
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import (
    INPUT_TYPE_GENERAL_INPUT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import (
    extract_json,
    generation_attend,
    make_script_dto,
    get_model_setting,
    get_script_ui_label,
)
from flaskr.service.study.models import UserGeneralInformation
from flaskr.dao import db
from flaskr.service.study.ui.input_general_input import (
    handle_input_general_input as handle_input_general_input_ui,
)
from flaskr.service.user.models import User
from flaskr.framework.plugin.plugin_manager import extensible_generic


def save_general_information(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    general_info: str,
):
    """保存用户的通用信息"""
    try:
        # 检查是否已存在相同的记录
        existing = UserGeneralInformation.query.filter(
            UserGeneralInformation.user_id == user_id,
            UserGeneralInformation.shifu_id == attend.course_id,
            UserGeneralInformation.shifu_outline_id == script_info.lesson_id,
            UserGeneralInformation.shifu_block_id == script_info.script_id,
        ).first()

        if existing:
            # 更新现有记录
            existing.general_information = general_info
            db.session.merge(existing)
        else:
            # 创建新记录
            new_info = UserGeneralInformation(
                user_id=user_id,
                general_information=general_info,
                shifu_id=attend.course_id,
                shifu_outline_id=script_info.lesson_id,
                shifu_block_id=script_info.script_id,
            )
            db.session.add(new_info)

        db.session.flush()
        app.logger.info(f"保存用户通用信息成功: user_id={user_id}, info={general_info}")
    except Exception as e:
        app.logger.error(f"保存用户通用信息失败: {e}")
        db.session.rollback()


def get_conversation_history(
    app: Flask,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    limit: int = 10,
):
    """获取最近的对话历史"""
    from flaskr.service.study.models import AICourseLessonAttendScript

    history = (
        AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.attend_id == attend.attend_id,
            AICourseLessonAttendScript.script_id == script_info.script_id,
        )
        .order_by(AICourseLessonAttendScript.created.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(history))  # 返回正序的历史记录


@register_input_handler(input_type=INPUT_TYPE_GENERAL_INPUT)
@extensible_generic
def handle_input_general_input(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    model_setting = get_model_setting(app, script_info)

    # 记录用户输入
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_conf = json.dumps(
        handle_input_general_input_ui(
            app, user_info, attend, script_info, input, trace, trace_args
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="general_input", input=input)

    # 获取对话历史
    history = get_conversation_history(app, attend, script_info)

    # 构建对话历史文本
    conversation_text = ""
    if len(history) >= 2:
        # 如果有历史记录，构建多轮对话
        for i, h in enumerate(history):
            role = "AI" if h.script_role == ROLE_TEACHER else "User"
            conversation_text += f"{role}: {h.script_content}\n"
        conversation_text += f"User: {input}"
    else:
        # 首次对话
        if len(history) == 1:
            conversation_text = f"AI: {history[0].script_content}\nUser: {input}"
        else:
            conversation_text = f"User: {input}"

    # 构建提示词
    prompt_template = """请从如下用户与AI的对话中总结出关于用户的个性化信息
如果没有任何个性化信息输出，请返回 json {"result":"原因","question":"继续追问用户得到正确的个性化信息"}
如果有的话，请返回 json {"result":"OK","info":"总结出的个性化信息"}
*****
以下是对话记录：

{}"""

    prompt = prompt_template.format(conversation_text)

    # 调用LLM分析
    resp = invoke_llm(
        app,
        user_info.user_id,
        span,
        model=model_setting.model_name,
        json=True,
        stream=True,
        message=prompt,
        generation_name="general_input_"
        + lesson.lesson_no
        + "_"
        + str(script_info.script_index)
        + "_"
        + script_info.script_name,
        **model_setting.model_args,
    )

    response_text = ""
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content

    # 解析响应
    jsonObj = extract_json(app, response_text)
    result = jsonObj.get("result", "")

    if result == "OK":
        # 保存个性化信息
        info = jsonObj.get("info", "")
        save_general_information(app, user_info.user_id, attend, script_info, info)

        app.logger.info("个性化信息提取成功，继续下一个块")
        span.end()
        db.session.flush()
        raise BreakException  # 继续执行下一个block
    else:
        # 继续追问用户
        question = jsonObj.get("question", "请提供更多信息以便我更好地了解您的需求。")

        # 返回追问内容给用户
        for text in question:
            yield make_script_dto(
                "text", text, script_info.script_id, script_info.lesson_id
            )
            time.sleep(0.01)

        # 记录AI的追问
        log_script = generation_attend(app, attend, script_info)
        log_script.script_content = question
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)

        span.end(output=response_text)
        trace_args["output"] = trace_args["output"] + "\r\n" + response_text
        trace.update(**trace_args)

        # 继续等待用户输入，不执行下一个block
        yield make_script_dto(
            "general-input",
            {"content": get_script_ui_label(app, script_info.script_ui_content)},
            script_info.script_id,
            script_info.lesson_id,
        )

        db.session.flush()
