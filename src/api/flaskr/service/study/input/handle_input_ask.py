import time
from trace import Trace
from flask import Flask
from flaskr.api.llm import chat_llm
from flaskr.service.study.const import INPUT_TYPE_ASK, ROLE_STUDENT, ROLE_TEACHER

from flaskr.service.study.models import AICourseLessonAttendScript
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_input_handler
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.study.utils import (
    get_follow_up_info,
    get_lesson_system,
    make_script_dto,
    get_fmt_prompt,
)
from flaskr.dao import db
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_with_llm_response,
    generation_attend,
)
from flaskr.service.user.models import User

from flaskr.service.rag.funs import (
    get_kb_list,
    retrieval_fun,
)
from flaskr.service.lesson.const import UI_TYPE_ASK


@register_input_handler(input_type=INPUT_TYPE_ASK)  # 注册问答类型的输入处理器
@extensible_generic
def handle_input_ask(
    app: Flask,  # Flask应用实例
    user_info: User,  # 用户信息
    lesson: AILesson,  # 课程信息
    attend: AICourseLessonAttend,  # 课程参与记录
    script_info: AILessonScript,  # 脚本信息
    input: str,  # 用户输入的问题
    trace: Trace,  # 追踪对象
    trace_args,  # 追踪参数
):
    """
    处理用户问答输入的主要函数
    负责处理用户在课程中的提问，并返回AI助教的回答
    """
    print("handle_input_ask", lesson.lesson_id, lesson.ask_prompt)

    # 获取后续跟进信息（包含问答提示词和模型配置）
    follow_up_info = get_follow_up_info(app, script_info)
    app.logger.info("follow_up_info:{}".format(follow_up_info.__json__()))

    # 查询历史对话记录，按时间顺序排列
    history_scripts = (
        AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.attend_id == attend.attend_id,
        )
        .order_by(AICourseLessonAttendScript.id.asc())
        .all()
    )

    messages = []  # 存储对话消息的列表
    input = input.replace("{", "{{").replace("}", "}}")  # 转义大括号，避免格式化冲突
    system_prompt = get_lesson_system(app, script_info.lesson_id)  # 获取课程系统提示词
    system_message = system_prompt if system_prompt else ""

    # 格式化课程问答提示词，插入系统提示词
    system_message = lesson.ask_prompt.format(shifu_system_message=system_message)
    messages.append({"role": "system", "content": system_message})  # 添加系统消息

    # 将历史对话记录添加到系统消息中
    for script in history_scripts:
        if script.script_role == ROLE_STUDENT:
            messages.append(
                {"role": "user", "content": script.script_content}
            )  # 添加系统消息
        elif script.script_role == ROLE_TEACHER:
            messages.append(
                {"role": "assistant", "content": script.script_content}
            )  # 添加系统消息

    # 开始知识库检索
    time_1 = time.time()
    retrieval_result_list = []  # 存储检索结果
    course_id = lesson.course_id
    my_filter = ""
    limit = 3  # 每个知识库最多返回3条结果
    output_fields = ["text"]  # 只返回文本字段

    # 获取课程相关的知识库列表
    kb_list = get_kb_list(app, [], [course_id])

    # 遍历每个知识库进行检索
    for kb in kb_list:
        retrieval_result = retrieval_fun(
            kb_id=kb["kb_id"],
            query=input,  # 使用用户输入作为查询
            my_filter=my_filter,
            limit=limit,
            output_fields=output_fields,
        )
        retrieval_result_list.append(retrieval_result)
        # break

    # 合并所有检索结果
    all_retrieval_result = "\n\n".join(retrieval_result_list)
    time_2 = time.time()
    app.logger.info(f"all retrieval_fun takes: {time_2 - time_1}s")
    app.logger.info(f"all_retrieval_result: {all_retrieval_result}")

    # 构建用户消息，包含检索到的相关知识
    messages.append(
        {
            "role": "user",
            "content": get_fmt_prompt(
                app,
                user_info.user_id,
                attend.course_id,
                follow_up_info.ask_prompt,  # 使用配置的问答提示词
                input=f"已知'{all_retrieval_result}'，请问'{input}'",  # 将检索结果和用户问题组合
            ),
        }
    )

    app.logger.info(f"messages: {messages}")

    # 获取后续问答使用的模型
    follow_up_model = follow_up_info.ask_model

    # 记录用户输入到数据库
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT  # 标记为学生角色
    log_script.script_ui_type = UI_TYPE_ASK  # 标记为问答类型
    db.session.add(log_script)

    # 创建追踪span
    span = trace.span(name="user_follow_up", input=input)

    # 格式化提示词，用于内容检查
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        attend.course_id,
        script_info.script_prompt,
        input,
        script_info.script_profile,
    )

    # 检查用户输入是否需要特殊处理（如敏感词过滤等）
    res = check_text_with_llm_response(
        app,
        user_info.user_id,
        log_script,
        input,
        span,
        lesson,
        script_info,
        attend,
        prompt,
    )

    try:
        # 如果检查结果不为空，直接返回检查结果
        first_value = next(res)
        app.logger.info("check_text_by_edun is not None")
        yield first_value
        yield from res
        db.session.flush()
        raise BreakException  # 抛出中断异常，结束处理
    except StopIteration:
        app.logger.info("check_text_by_edun is None ,invoke_llm")

    # 调用LLM生成回答
    resp = chat_llm(
        app,
        user_info.user_id,
        span,
        model=follow_up_model,  # 使用配置的模型
        json=True,
        stream=True,  # 启用流式输出
        temperature=script_info.script_temperature,  # 使用配置的温度参数
        generation_name="user_follow_ask_"  # 生成任务的名称
        + lesson.lesson_no
        + "_"
        + str(script_info.script_index)
        + "_"
        + script_info.script_name,
        messages=messages,  # 传入完整的对话历史
    )

    response_text = ""  # 存储完整的回答文本
    # 流式处理LLM响应
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            # 实时返回每个文本片段
            yield make_script_dto(
                "text", i.result, script_info.script_id, script_info.lesson_id
            )

    # 记录AI回答到数据库
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = response_text
    log_script.script_role = ROLE_TEACHER  # 标记为老师角色
    log_script.script_ui_type = UI_TYPE_ASK  # 标记为问答类型
    db.session.add(log_script)

    # 结束追踪span
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()

    # 返回结束标记
    yield make_script_dto(
        "text_end", "", script_info.script_id, script_info.lesson_id, log_script.log_id
    )
