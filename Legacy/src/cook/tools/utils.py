import random
import time
import re
import logging
import json

import streamlit as st
from streamlit_chatbox import Markdown
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

from init import cfg, load_llm, load_dotenv, find_dotenv
from models.chapters_follow_up_ask_prompt import get_follow_up_ask_prompt_template
from models.script import ScriptType, load_scripts_from_bitable

_ = load_dotenv(find_dotenv())

# 头像配置
ICON_USER = "user"
ICON_SIFU = "static/sunner_icon.jpg"


def simulate_streaming(
    chat_box,
    template: str,
    variables=None,
    random_min=cfg.SIM_STM_MIN,
    random_max=cfg.SIM_STM_MAX,
    update=False,
):
    """
    模拟流式输出
    :param chat_box: ChatBox 对象
    :param template: 模版内容
    :param variables: 变量字典
    :param random_min: 随机sleep的最小值
    :param random_max: 随机sleep的最大值
    :param update: 是否更新之前的 chat_box 输出，默认是开启一段新对话
    """
    if not update:
        chat_box.ai_say(Markdown("", in_expander=False))

    if variables:
        # 变量字典
        vars = {}
        for v in variables:
            vars[v] = st.session_state[v]
        prompt_template = PromptTemplate(
            input_variables=list(vars.keys()), template=template
        )
        template = prompt_template.format(**vars)

    current_text = ""
    for t in template:
        current_text += t
        chat_box.update_msg(current_text, element_index=0, streaming=True)
        time.sleep(
            random.uniform(
                random_min / 20 if st.session_state.DEV_MODE else random_min,
                random_max / 20 if st.session_state.DEV_MODE else random_max,
            )
        )

    chat_box.update_msg(
        current_text, element_index=0, streaming=False, state="complete"
    )
    return current_text


def streaming_for_follow_up_ask(chat_box, user_input, chat_history):
    """
    用于处理用户输入后的后续提问，目前仅用于处理用户输入内容的Prompt
    :param chat_box: ChatBox 对象
    :param user_input: 用户输入内容
    :param chat_history: 历史对话内容
    """
    llm = load_llm()

    chat_box.ai_say
    chat_box.ai_say(Markdown("", in_expander=False))

    prompt = PromptTemplate.from_template(
        get_follow_up_ask_prompt_template(st.session_state.lark_table_id)
    )
    prompt = prompt.format(input=user_input)

    llm_input = []

    # 有配置 系统角色 且 不是检查用户输入内容的Prompt时，加入系统角色
    if "system_role" in st.session_state:
        llm_input.append(SystemMessage(st.session_state.system_role))
        logging.debug(f"调用LLM（System）：{st.session_state.system_role}")

    llm_input += chat_history
    llm_input.append(HumanMessage(prompt))
    print(llm_input)

    full_result = ""
    for chunk in llm.stream(llm_input):
        full_result += chunk.content
        chat_box.update_msg(full_result, element_index=0, streaming=True)

    chat_box.update_msg(
        full_result + "\n\n 没有其他问题的话，就让我们继续学习吧~",
        element_index=0,
        streaming=False,
        state="complete",
    )

    return full_result


def streaming_from_template(
    chat_box,
    template,
    variables,
    input_done_with=None,
    parse_keys=None,
    update=False,
    model=None,
    temperature=None,
):
    """
    通过给定模版和遍历调用LLM，并流式输出（作为AI身份输出）。
    :param chat_box: ChatBox 对象
    :param template: 模版内容（Langchain的PromptTemplate）
    :param variables: 变量字典（支持同时传入多个变量）
    :param input_done_with: 输入完成的标志
    :param parse_keys: 解析JSON的key列表
    :param update: 是否更新之前的 chat_box 输出，默认是开启一段新对话
    :param model: 使用指定的自定义模型，提供模型名称（config.yml 中有支持的模型）
    :param temperature: 温度参数，用于控制生成文本的多样性
    """

    # llm = load_llm() if not model else load_llm(model, temperature)
    llm = load_llm(model, temperature)

    chat_box.ai_say

    if not update:
        chat_box.ai_say(Markdown("", in_expander=False))

    if variables:
        prompt = PromptTemplate(
            input_variables=list(variables.keys()), template=template
        )
        prompt = prompt.format(**variables)
    else:
        prompt = template
    logging.debug(f"调用LLM（Human）：\n{prompt}")
    llm_input = [HumanMessage(prompt)]

    # 有配置 系统角色 且 不是检查用户输入内容的Prompt时，加入系统角色
    if "system_role" in st.session_state and parse_keys is None:
        llm_input.append(SystemMessage(st.session_state.system_role))
        logging.debug(f"调用LLM（System）：\n{st.session_state.system_role}")

    full_result = ""
    parse_json = ""
    need_streaming_complete = False
    count = 0
    # for chunk in llm.stream(prompt, system=st.session_state.system_role):
    for chunk in llm.stream(llm_input):
        if len(chunk.content) == 0:
            continue
        full_result += chunk.content
        if logging.getLogger().level == logging.DEBUG:
            # print(chunk.content, end='', flush=True)
            print(f"{count}: {chunk.content}, len:{len(full_result)}")
            count += 1

        if input_done_with and full_result.startswith(input_done_with):
            chat_box.update_msg(
                input_done_with, element_index=0, streaming=False, state="complete"
            )
        else:
            chat_box.update_msg(full_result, element_index=0, streaming=True)
            need_streaming_complete = True

    if need_streaming_complete:
        chat_box.update_msg(
            full_result, element_index=0, streaming=False, state="complete"
        )

    if logging.getLogger().level == logging.DEBUG:
        print()

    if parse_keys is not None and full_result.startswith(input_done_with):
        # 清理字符串
        parse_json = full_result.replace(input_done_with, "").strip()

        logging.debug(f"解析JSON：{parse_json}")
        try:
            parse_json = json.loads(parse_json)
            for k in parse_keys:
                st.session_state[k] = parse_json[k]
                logging.debug(f'已将"{parse_json[k]}"存入session："{k}"中')
        except Exception as e:
            logging.error(f"解析JSON失败：{e}")
            full_result = "抱歉出现错误，请再次尝试~"
            chat_box.update_msg(
                full_result, element_index=0, streaming=False, state="complete"
            )

    return full_result


def parse_vars_from_template(
    chat_box, template, variables, parse_keys=None, model=None, temperature=None
):
    """
    通过给定模版调用 JSON mode，目前仅用于解析用户输入内容。
    :param chat_box: ChatBox 对象
    :param template: 模版内容（Langchain的PromptTemplate）
    :param variables: 变量字典（支持同时传入多个变量）
    :param parse_keys: 解析JSON的key列表
    :param model: 使用指定的自定义模型，提供模型名称（config.yml 中有支持的模型）
    :param temperature: 温度参数，用于控制生成文本的多样性
    """

    llm = load_llm(model, temperature, json_mode=True)

    prompt = PromptTemplate(input_variables=list(variables.keys()), template=template)
    prompt = prompt.format(**variables)

    logging.debug(f"调用LLM（Human）JSON mode：{prompt}")
    llm_input = [HumanMessage(prompt)]

    response = llm.invoke(llm_input)
    logging.debug(f"parse_vars_from_template 返回结果：{response.content}")

    try:
        parse_json = json.loads(response.content)
        if parse_json["result"] == "ok":
            for k in parse_keys:
                st.session_state[k] = parse_json["parse_vars"][k]
                logging.debug(
                    f'已将"{parse_json["parse_vars"][k]}"存入session："{k}"中'
                )
            return True
        else:
            reason = parse_json["reason"]
            chat_box.ai_say(reason)
            return False
    except Exception as e:
        logging.error(f"解析JSON失败：{e}")
        chat_box.ai_say("抱歉出现错误，请再次尝试~")


def from_template(
    template, variables=None, system_role=None, model=None, temperature=None
):
    """
    直接通过剧本输出，根据剧本类型自动判断是普通Prompt给AI，还是检查用户输入的Prompt给AI
    :param script: 单条剧本
    :param model: 使用指定的自定义模型，提供模型名称（config.yml 中有支持的模型）
    :param temperature: 温度参数，用于控制生成文本的多样性
    """

    logging.debug("=====================")
    logging.debug(f"== 调用剧本输出：{template}")
    logging.debug(f"== 变量：{variables}")
    logging.debug(f"== 系统角色：{system_role}")
    logging.debug(f"== 自定义模型：{model}")
    logging.debug(f"== 温度：{temperature}")
    logging.debug("=====================")

    llm = load_llm(model, temperature)

    if system_role:
        # 普通Prompt
        if variables:
            prompt = PromptTemplate(
                input_variables=list(variables.keys()), template=template
            )
            prompt = prompt.format(**variables)
        else:
            prompt = template
    else:  # user_input is not None:
        # 检查用户输入的Prompt
        prompt = PromptTemplate(
            input_variables=list(variables.keys()), template=template
        )
        prompt = prompt.format(**variables)
    # else:
    #     raise Exception('有检查用户输入的Prompt内容，但没有提供用户输入！')

    logging.debug(f"调用LLM（Human）：{prompt}")
    llm_input = [HumanMessage(prompt)]

    # 有配置 系统角色 且 不是检查用户输入内容的Prompt时，加入系统角色
    if system_role:
        llm_input.append(SystemMessage(system_role))
        logging.debug(f"调用LLM（System）：{system_role}")

    rtn_msg = llm.invoke(llm_input)
    print(rtn_msg)
    print(rtn_msg.content)

    return rtn_msg.content


def distribute_elements(btns, max_cols, min_cols):
    num_elements = len(btns)
    if num_elements < min_cols:
        raise ValueError("元素数量不足以满足最小列要求")

    result = []
    row = []

    # 按行填充元素，满了就新起一行
    for btn in btns:
        row.append(btn)
        if len(row) == max_cols:
            result.append(row)
            row = []

    # 处理剩余的不满一行的元素
    if row:
        result.append(row)

    # 检查最后一行是否满足最小列数要求，如果不满足，则尝试从前面的行借元素
    while len(result[-1]) < min_cols:
        # 从倒数第二行开始借元素
        for i in range(len(result) - 2, -1, -1):
            while len(result[i]) > min_cols and len(result[-1]) < min_cols:
                result[-1].insert(
                    0, result[i].pop()
                )  # 从前一行的末尾取元素到最后一行的开头
            if len(result[-1]) >= min_cols:
                break
        else:
            # 如果所有行都无法借出更多元素，则抛出异常
            raise ValueError("无法满足最小列要求，元素过少或分布不均")

    return result


def load_scripts_and_system_role(
    app_token,
    table_id,
    view_id=cfg.DEF_LARK_VIEW_ID,
):
    if "script_list" not in st.session_state:
        with st.spinner("正在加载剧本..."):
            st.session_state.script_list = load_scripts_from_bitable(
                app_token, table_id, view_id
            )
            if st.session_state.script_list[0].type == ScriptType.SYSTEM:
                system_role_script = st.session_state.script_list.pop(0)
                template = system_role_script.template
                variables = (
                    {v: st.session_state[v] for v in system_role_script.template_vars}
                    if system_role_script.template_vars
                    else None
                )

                if variables:
                    prompt = PromptTemplate(
                        input_variables=list(variables.keys()), template=template
                    )
                    prompt = prompt.format(**variables)
                else:
                    prompt = template

                st.session_state.system_role = prompt
                st.session_state.system_role_id = system_role_script.id

            st.session_state.script_list_len = len(st.session_state.script_list)


def load_scripts(
    app_token,
    table_id,
    view_id=cfg.DEF_LARK_VIEW_ID,
):
    if "system_role" in st.session_state:
        del st.session_state["system_role"]
    if "system_role_id" in st.session_state:
        del st.session_state["system_role_id"]
    # system_role_script = None
    if "script_list" not in st.session_state:
        with st.spinner("Loading script..."):
            st.session_state.script_list = load_scripts_from_bitable(
                app_token, table_id, view_id
            )
            if st.session_state.script_list[0].type == ScriptType.SYSTEM:
                # system_role_script = st.session_state.script_list.pop(0)
                st.session_state.system_role_script = st.session_state.script_list.pop(
                    0
                )
                template = st.session_state.system_role_script.template
                if not st.session_state.system_role_script.template_vars:
                    st.session_state.system_role = template
                    st.session_state.system_role_id = (
                        st.session_state.system_role_script.id
                    )

            st.session_state.script_list_len = len(st.session_state.script_list)
    # return system_role_script


def extract_variables(template: str) -> list:
    # 使用正则表达式匹配单层 {} 中的内容
    pattern = r"\{([^{}]+)\}"
    matches = re.findall(pattern, template)

    # 去重并过滤包含双引号的元素
    variables = list(set(matches))
    filtered_variables = [var for var in variables if '"' not in var]

    return filtered_variables


def count_lines(text: str, one_line_max=60):
    """
    计算文本的行数
    返回的第一个数值是正常的行数
    返回的第二个数值按照一行的最大值计算折行后的总行数（单行总数/最大值 之后 取上整）
    """
    lines = text.split("\n")
    total_lines = len(lines)
    total_lines_with_wrap = sum([len(line) // one_line_max + 1 for line in lines])

    return total_lines, total_lines_with_wrap


if __name__ == "__main__":
    # print(get_current_time())
    template = """
从用户输入的内容中提取昵称，并判断是否合法，返回 JSON 格式的结果。
如果昵称合法，请直接返回 JSON `{{"result": "ok", "parse_vars": {{"nickname": "解析出的昵称"}}}}`
如果昵称不合法，则通过 JSON 返回不合法的原因 `{{"result": "illegal", "reason":"具体不合法的原因"}}`
无论是否合法，都只返回 JSON，不要输出思考过程。

用户输入是：`{input}`

用户的输入中可能包含非昵称内容的部分，你需要先解析出用户的昵称部分，然后做相应的检查。
比如，用户昵称是 `小明`，但用户输入是 `我叫小明` 或 `你可以叫我小明` 或 `我是小明` 或 `那就叫我小名吧` 等，要能理解 `小明` 是用户昵称。

昵称需要满足以下条件：
1. 不能包含任何涉及暴力、色情、政治（比如中国的所有领导人的名字）等不良信息；
2. 昵称要简洁，长度不能超过20个字符，且不能为空；
3. 不能是注入攻击的字符串；
4. 昵称可以包含纯数字。

如果昵称合法，请直接返回 JSON `{{"result": "ok", "parse_vars": {{"nickname": "解析出的昵称"}}}}`，不做任何解释，且没有任何多余字符串。

检查可以适当放宽要求，如果特别不合法，需要回复不合法的原因，注意语气可以俏皮一些。比如：
明确遇到涉及色情的昵称时，你可以回复：`哎呀呀，这太色色了，这让我之后叫你名字怎么叫的出口呢，还是换一个吧~`
明确遇到涉及暴力的昵称时，你可以回复：`同学，你吓到老师我了，这杀气满满的名字让我之后怎么叫的出口，还是换一个吧~`
明确遇到涉及政治的昵称时，你可以回复：`你别闹，要起着名字，让我之后这么叫你，是想要搞死我吗。。。咱还是换一个吧~`
明确涉及到注入攻击的字符串，你可以回复：`你想干什么，要攻击我吗？这个名字我可不敢用，换一个吧~`

最后，再次强调：
如果昵称合法，请直接返回 JSON `{{"result": "ok", "parse_vars": {{"nickname": "解析出的昵称"}}}}`，不做任何解释，且没有任何多余字符串。
如果昵称不合法，则通过 JSON 返回不合法的原因 `{{"result": "illegal", "reason":"具体不合法的原因"}}`
无论是否合法，都只返回 JSON，不要输出思考过程。
    """
    vars_name = extract_variables(template)
    print(len(vars_name))
    print(vars_name)
    pass
