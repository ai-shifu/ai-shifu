from streamlit_extras.bottom_container import bottom

from models.course import get_courses_by_user_from_sqlite
from tools.lark import get_bitable_tables
from tools.utils import *
from tools.dev_tools import *
from models.script import *
from tools.auth import login


# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="CodeSifu",
    page_icon="🧙‍♂️",  # 👨‍🏫
)
# 固定侧边栏宽度并添加Logo
fix_sidebar_add_logo("static/CodeSifu_logo_w300.jpg")
# 页面内的大标题小标题
'# Code Sifu ⌨️🧙‍♂️⌨️'  # 📚
st.caption('📚 你的专属AI编程私教')


# ========== Debug 初始化 ==========
# 日志级别设置
logging.basicConfig(level=logging.DEBUG)  # 如需要更细致的观察run状态时可以将 `level` 的值改为 `logging.DEBUG`
# 是否开启开发模式
st.session_state.DEV_MODE = True if st.query_params.get('dev') else False
logging.info(f'DEV_MODE: {st.session_state.DEV_MODE}')

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

if 'has_started' not in st.session_state:
    st.session_state.has_started = False

# if 'lark_app_token' not in st.session_state:
#     st.session_state.lark_app_token = ''

# ======================================================

# ==================== Sidebar ====================
with st.sidebar:
    if st.button('Clean all cache', use_container_width=True):
        st.cache_data.clear()


# ==================== 主体框架 ====================
# 需要登录
if login():

    # 开发者模式要做的事情
    if st.session_state.DEV_MODE:
        # 加载进度控制器
        load_process_controller()

    if not st.session_state.has_started:
        courses = get_courses_by_user_from_sqlite(st.session_state["username"])

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            selected_course = st.selectbox('选择课程:', (course.course_name for course in courses))

        if selected_course:
            st.session_state.lark_app_token = next(
                (course.lark_app_token for course in courses if course.course_name == selected_course), None)
            tables = get_bitable_tables(st.session_state.lark_app_token)

            with col2:
                select_table = st.selectbox('选择剧本:', (
                    table.name for table in tables if not table.name.startswith('字典-')))

            with col3:
                select_progress = st.number_input('开始位置:', value=2, min_value=1, step=1)


        if st.button('启动剧本', type='primary', use_container_width=True):
            st.session_state.lark_table_id = next(
                (table.table_id for table in tables if table.name == select_table), None)
            st.session_state.has_started = True
            st.rerun()



    # 非开发者模式直接开始，若在开发者模式则等待配置后开始
    # if not st.session_state.DEV_MODE or st.session_state.has_started:
    if st.session_state.has_started:

            # 加载剧本及系统角色
            load_scripts_and_system_role(st.session_state.lark_app_token, st.session_state.lark_table_id)
            st.session_state.progress = select_progress - (2 if 'system_role' in st.session_state else 1)

            # 获取剧本总长度，并在结束时停止
            if st.session_state.progress >= st.session_state.script_list_len:
                # chat_box.ai_say('别再犹豫了，马上把我带回家吧~')
                with bottom():
                    st.write('')
                st.stop()

            # 根据当前进度ID，获取对应的剧本
            script: Script = st.session_state.script_list[st.session_state.progress]
            logging.debug(f'当前剧本：\n{script}')
            if st.session_state.DEV_MODE:
                show_current_script(script)


            # ========== 内容输出部分 ==========
            # 如果剧本没有输出过，则进行输出
            if script.id not in st.session_state.script_has_output:
                full_result = None

                # ===【固定剧本】：模拟流式输出
                if script.type == ScriptType.FIXED:
                    if script.format == ScriptFormat.MARKDOWN:
                        full_result = simulate_streaming(chat_box, script.template, script.template_vars)
                    elif script.format == ScriptFormat.IMAGE:
                        chat_box.ai_say(Image(script.media_url))
                        full_result = script.media_url

                # == 【Prompt】：剧本内容提交给 LLM，获得AI回复输出
                elif script.type == ScriptType.PROMPT:
                    full_result = streaming_from_template(
                        chat_box, script.template,
                        {v: st.session_state[v] for v in script.template_vars} if script.template_vars else None,
                        model=script.custom_model, temperature=script.temperature
                    )

                # 最后记录下已输出的剧本ID，避免重复输出
                st.session_state.script_has_output.add(script.id)
                logging.debug(f'script id: {script.id}, chat result: {full_result}')


            # ========== 处理【后续交互】 ==========
            # === 显示 输入框
            if script.next_action == NextAction.ShowInput:
                # 获取用户输入
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # 展示用户输入信息

                    # 通过 `检查模版` 提取变量（JSON mode）
                    is_ok = parse_vars_from_template(chat_box, script.check_template, {'input': user_input},
                                                     parse_keys=script.parse_vars,
                                                     model=script.custom_model, temperature=script.temperature)

                    # 如果正常执行，则进入下一个剧本
                    if is_ok:
                        st.session_state.progress += 1
                        st.rerun()

            # === 显示 按钮
            elif script.next_action == NextAction.ShowBtn:
                with bottom():
                    if st.button(script.btn_label, type='primary', use_container_width=True):
                        st.session_state.progress += 1
                        st.rerun()

            # === 显示 按钮组
            elif script.next_action == NextAction.ShowBtnGroup:
                with bottom():
                    btns = distribute_elements(script.btn_group_cfg['btns'], 3, 2)
                    for row in btns:
                        st_cols = st.columns(len(row))
                        for i, btn in enumerate(row):
                            if st_cols[i].button(btn['label'], key=btn['value'], type='primary', use_container_width=True):
                                # 获取用户点击按钮的 value
                                st.session_state[script.btn_group_cfg['var_name']] = btn['value']
                                st.session_state.progress += 1
                                st.rerun()

            # === 跳转按钮
            elif script.next_action == NextAction.JumpBtn:
                if st.button(script.btn_label, type='primary', use_container_width=True):
                    # 获取需要判断的变量值
                    var_value = st.session_state.get(script.btn_jump_cfg['var_name'])
                    # == 如果是静默跳转
                    if script.btn_jump_cfg['jump_type'] == 'silent':
                        # 找到要跳转的子剧本
                        lark_table_id, lark_view_id = None, None
                        for jump_rule in script.btn_jump_cfg['jump_rule']:
                            if var_value == jump_rule['value']:
                                lark_table_id = jump_rule['lark_table_id']
                                lark_view_id = jump_rule['lark_view_id']

                        # 如果找到了则加载，否则报错
                        if lark_table_id:
                            sub_script_list = load_scripts_from_bitable(cfg.LARK_APP_TOKEN, lark_table_id, lark_view_id)
                            # 将子剧本插入到原剧本中
                            st.session_state.script_list = (
                                    st.session_state.script_list[:st.session_state.progress + 1]
                                    + sub_script_list
                                    + st.session_state.script_list[st.session_state.progress + 1:]
                            )
                            # 更新剧本总长度
                            st.session_state.script_list_len = len(st.session_state.script_list)
                            # 更新剧本进度
                            st.session_state.progress += 1
                            # 重新运行
                            st.rerun()

                        else:
                            raise ValueError('未找到对应的子剧本')

            # === 显示 付款码
            elif script.next_action == NextAction.ShowPayQR:
                pass

            # === 输入 手机号
            elif script.next_action == NextAction.InputPhoneNum:
                # 获取用户输入
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # 展示用户输入信息

                    # 暂时不做任何处理，直接下一步
                    st.info('暂时不做任何处理，直接下一步', icon="ℹ️")
                    time.sleep(1)
                    st.session_state.progress += 1
                    st.rerun()

            # === 输入 验证码
            elif script.next_action == NextAction.InputVerifyCode:
                # 获取用户输入
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # 展示用户输入信息

                    # 暂时不做任何处理，直接下一步
                    st.info('暂时不做任何处理，直接下一步', icon="ℹ️")
                    time.sleep(1)
                    st.session_state.progress += 1
                    st.rerun()

            else:
                st.session_state.progress += 1
                st.rerun()


