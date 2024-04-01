import json
import logging
import random

from streamlit_chatbox import *
from langchain_openai import ChatOpenAI

from tools.utils import *
# from prompt import trial, agent
from script import *

# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="CodeSifu",
    page_icon="🧙‍♂️",  # 👨‍🏫
)
# 页面内的大标题小标题
'# Code Sifu ⌨️🧙‍♂️⌨️'  # 📚
st.caption('📚 你的专属AI编程私教')

# 日志级别设置
logging.basicConfig(level=logging.DEBUG)  # 如需要更细致的观察run状态时可以将 `level` 的值改为 `logging.DEBUG`

# ========== chat_box 初始化 ==========
chat_box = ChatBox(assistant_avatar=ICON_SIFU)
chat_box.init_session()
chat_box.output_messages()

# ========== session 初始化 ==========
# 初始化进展ID
if 'progress' not in st.session_state:
    st.session_state.progress = 0

# 记录剧本是否输出
if 'script_has_output' not in st.session_state:
    st.session_state.script_has_output = set()

# ========== 侧边栏 初始化 ==========
# 初始化侧边栏
with st.sidebar:
    st.subheader('CodeSifu Configuration')
    st.write(f'当前进度：{st.session_state.progress}')

# ======================================================


# ==================== 主体框架 ====================
# 获取剧本总长度，并在结束时提示
script_len = len(SCRIPT_LIST)
if st.session_state.progress >= script_len:
    chat_box.ai_say('别再犹豫了，马上把我带回家吧~')
    st.stop()

# 根据当前进度ID，获取对应的剧本
script = SCRIPT_LIST[st.session_state.progress]
logging.debug(f'当前剧本：\n{script}')


# ========== 内容输出部分 ==========
# 如果剧本没有输出过，则进行输出
if script['id'] not in st.session_state.script_has_output:
    if script['type'] == Type.FIXED:
        if script['format'] == Format.MARKDOWN:
            full_result = simulate_streaming(chat_box, script['template'], script['template_vars'])
        elif script['format'] == Format.IMAGE:
            chat_box.ai_say(Image(script['media_url']))
            full_result = script['media_url']
    elif script['type'] == Type.PROMPT:
        full_result = streaming_from_template(chat_box, script['template'], {v: st.session_state[v] for v in script['template_vars']})
    # elif script['type'] == Type.XXXX:  # TODO: 其他类型？
    else:
        full_result = None
    logging.debug(f'script id: {script["id"]}, chat result: {full_result}')

    # 记录已输出的剧本ID，避免重复输出
    st.session_state.script_has_output.add(script['id'])


# ========== 交互区域部分 ==========
if script['show_input']:
    if user_input := st.chat_input(script['input_placeholder']):
        chat_box.user_say(user_input)
        
        full_result = streaming_from_template(chat_box, script['check_input'], {'input': user_input},
                                              input_done_with=script['input_done_with'],
                                              parse_keys=script['parse_keys'])
        logging.debug(f'scrip id: {script["id"]}, chat result: {full_result}')
        
        if full_result.startswith(script['input_done_with']):
            if script['input_for'] == InputFor.SAVE_PROFILE:
                st.session_state[script['save_key']] = user_input
                logging.debug(f'保存用户输入：{script["save_key"]} = {user_input}')
            
            st.session_state.progress += 1
            st.rerun()
elif script['show_btn']:
    if st.button(script['btn_label'], type=script['btn_type'], use_container_width=script['use_container_width']):
        if script['btn_for'] == BtnFor.CONTINUE:
            st.session_state.progress += 1
            st.rerun()
        elif 1:
            pass  # TODO 其他可能的按钮操作
else:
    st.session_state.progress += 1
    st.rerun()


