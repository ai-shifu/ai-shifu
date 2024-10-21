import time

from flask import Flask

from flaskr.service.study.models import AICourseLessonAttendScript
from flaskr.api.llm import invoke_llm
from flaskr.api.check.edun import (
    EDUN_RESULT_SUGGESTION_PASS,
    EDUN_RESULT_SUGGESTION_REJECT,
    RISK_LABLES,
    check_text,
)
from flaskr.service.study.utils import generation_attend
from flaskr.service.check_risk import add_risk_control_result
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import (
    ROLE_TEACHER,
)
from flaskr.dao import db
from flaskr.service.study.utils import make_script_dto


class BreakException(Exception):
    pass


def check_text_by_edun(
    app: Flask,
    user_id: str,
    log_script: AICourseLessonAttendScript,
    input: str,
    span,
    script_info: AILessonScript,
    attend: AICourseLessonAttend,
):
    res = check_text(log_script.log_id, input)
    span.event(name="check_text", input=input, output=res)
    result = (
        res.get("result", {})
        .get("antispam", {})
        .get("suggestion", EDUN_RESULT_SUGGESTION_PASS)
    )
    add_risk_control_result(
        app,
        log_script.log_id,
        user_id,
        input,
        "edun",
        str(res),
        "",
        result,
        "check_text",
    )
    if result == EDUN_RESULT_SUGGESTION_REJECT:
        label = res.get("result", {}).get("antispam", {}).get("label", 100)
        text = RISK_LABLES.get(label, "")
        prompt = "你是一名在线老师,要回答学生的相应提问，目前学生的问题有一些不合规不合法的地方，请找一个合适的理由拒绝学生，当前的教学内容为:{},学生的问题为：{},拒绝的理由为：{}".format(
            script_info.script_prompt, input, text
        )
        res = invoke_llm(
            app,
            span,
            message=prompt,
            model=script_info.script_model,
            json=False,
            stream=True,
        )
        response_text = ""
        for i in res:
            yield make_script_dto("text", i.result, script_info.script_id)
            response_text += i.result
            time.sleep(0.01)
        log_script = generation_attend(app, attend, script_info)
        log_script.script_content = response_text
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        db.session.flush()
        yield make_script_dto("text_end", "", script_info.script_id)
    else:
        app.logger.info("check_text_by_edun is None")
        return
