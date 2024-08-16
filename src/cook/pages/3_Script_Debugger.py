from uuid import uuid4
import concurrent.futures

from tools.auth import login
from tools.utils import *
from tools.dev_tools import *
from models.script import *
from init import cfg

_ = load_dotenv(find_dotenv())


# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="Script Debugger",
    page_icon="🧙‍♂️",
    initial_sidebar_state="collapsed",
    layout="wide",
    menu_items={
        'Get Help': 'https://www.extremelycoolapp.com/help',
        'Report a bug': "https://www.extremelycoolapp.com/bug",
        'About': "# This is a header. This is an *extremely* cool app!"
    }
)

# 页面内的大标题小标题
'# 剧本调试器 🐞📜🐞'
st.caption('')

# 需要登录
if login():

    # 初始化要调试的模型列表
    if 'debug_models' not in st.session_state:
        st.session_state.debug_models = []

    # 初始化要调试的单条剧本
    if 'debug_script' not in st.session_state:
        st.session_state.debug_script = None

    #
    # nickname = st.query_params.get('nickname')
    # industry = st.query_params.get('industry')
    # occupation = st.query_params.get('occupation')
    # ai_tools = st.query_params.get('ai_tools')
    # table = st.query_params.get('table')
    #
    # if progress := st.query_params.get('progress'):
    #     st.session_state.progress = int(progress) - 1
    #     st.session_state.nickname = nickname if nickname else '小明'
    #     st.session_state.industry = industry if industry else '互联网'
    #     st.session_state.occupation = occupation if occupation else '产品经理'
    #     st.session_state.ai_tools = ai_tools if ai_tools else 'GitHub_Copilot'
    #     st.session_state.table = table if table else None
    #     if st.session_state.table:
    #         load_scripts_and_system_role(cfg.LARK_APP_TOKEN, st.session_state.table, cfg.DEF_LARK_VIEW_ID)
    #         if 'system_role' in st.session_state:
    #             st.session_state.progress -= 1
    #         logging.debug(f'从 {st.session_state.progress} 开始剧本（{st.session_state.table}）')
    #     else:
    #         logging.debug(f'从 {st.session_state.progress} 开始默认剧本（{cfg.DEF_LARK_TABLE_ID}）')
    #     st.session_state.has_started = True
    #     st.rerun()


    # =========================================================
    # ===== 配置 用户Profile
    col1, col2, col3, col4, col5 = st.columns(5, gap='small')
    with col1:
        st.session_state.nickname = st.text_input('默认昵称', value='小明')
    with col2:
        st.session_state.industry = st.text_input('默认行业', value='互联网')
    with col3:
        st.session_state.occupation = st.text_input('默认职业', value='产品经理')
    with col4:
        st.session_state.ai_tools = st.text_input('默认AI工具', value='GitHub_Copilot')
    with col5:
        st.session_state.style = st.selectbox('默认风格', ('幽默风趣', '严肃专业', '鼓励温暖'))
    # with col2:
        # with st.expander('默认 LLM 配置'):
        #     cfg.set_default_model(st.selectbox('默认 LLM：', cfg.SUPPORT_MODELS,
        #                                        index=cfg.SUPPORT_MODELS.index(cfg.DEFAULT_MODEL)))
        #     cfg.set_qianfan_default_temperature(st.number_input('QianFan 默认温度：', value=cfg.QIANFAN_DEF_TMP))
        #     cfg.set_openai_default_temperature(st.number_input('OpenAI 默认温度：', value=cfg.OPENAI_DEF_TMP))


    # =========================================================
    # ===== 加载 指定单条剧本
    col1, col2 = st.columns([0.7, 0.3], gap='small')
    with col1:
        chapter = st.selectbox('选择剧本：', load_chapters_from_sqlite())
    with col2:
        progress = st.number_input('开始位置：', value=2, min_value=1, step=1) - 2

    if st.button(f'加载剧本', type='primary', use_container_width=True):
        # 加载剧本及系统角色
        load_scripts_and_system_role(cfg.LARK_APP_TOKEN, chapter.lark_table_id, chapter.lark_view_id)
        progress += 1 if 'system_role' not in st.session_state else 0
        st.session_state.progress = progress
        logging.debug(f'从 {st.session_state.progress} 开始剧本')
        script: Script = st.session_state.script_list[progress]
        st.session_state.debug_script = script

        with st.expander('剧本详情'):
            st.write(script)

        if 'system_role' in st.session_state:
            with st.expander('系统角色'):
                st.text_area('系统角色', st.session_state.system_role, height=200, label_visibility='hidden')

        if script.type == ScriptType.FIXED and script.check_template == '未填写！':
            st.error('该剧本为固定剧本，且没有用户输入需要检查，不需要测试！')
        else:
            edited_template = st.text_area('模版内容', script.template, height=200)
            st.write(f"模版内容共计 {len(edited_template)} 个字符")
            if script.check_template != '未填写！':
                edited_check_template = st.text_area('检查模版内容', script.check_template, height=200)
                st.write(f"检查模版内容共计 {len(edited_check_template)} 个字符")



    # =========================================================
    # ===== 配置 要调试的模型
    st.write('## 模型配置')
    col1, col2 = st.columns(2, gap='medium')
    with col1:
        models = []
        model = st.selectbox('选择模型：', cfg.SUPPORT_MODELS, index=cfg.SUPPORT_MODELS.index(cfg.DEFAULT_MODEL))
        temperature = 0
        if model in cfg.QIANFAN_MODELS:
            temperature = cfg.QIANFAN_DEF_TMP
        elif model in cfg.ZHIPU_MODELS:
            temperature = cfg.ZHIPU_DEF_TMP
        elif model in cfg.OPENAI_MODELS:
            temperature = cfg.OPENAI_DEF_TMP
        temperature = st.number_input('设定温度：', value=temperature)
        if st.button('添加测试模型 -->',  use_container_width=True):
            if (model, temperature) not in st.session_state.debug_models:
                st.session_state.debug_models.append((model, temperature))
    with col2:
        df_models = st.dataframe(
            st.session_state.debug_models,
            column_config={
                1: "模型",
                2: "温度",
            },
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode=["multi-row", "multi-column"],
        )

        select_rows: list = df_models.selection['rows']
        if select_rows:
            # .write(f'选中的行：{select_rows}')
            if st.button(f'删除选中行：{select_rows}', use_container_width=True):
                select_rows.sort(reverse=True)
                for row in select_rows:
                    if row < len(st.session_state.debug_models):
                        st.session_state.debug_models.pop(row)
                    else:
                        st.error(f"无效的行索引: {row}")
                st.rerun()


    # =========================================================
    # ===== 开始测试
    def debug_model(model, temperature, script, system_role):
        # ========== chat_box 初始化 ==========
        chat_box = ChatBox(assistant_avatar=ICON_SIFU, session_key=str(uuid4()))
        chat_box.init_session()
        chat_box.output_messages()

        st.session_state.system_role = system_role

        if script.check_template != '未填写！':
            full_result = streaming_from_template(
                chat_box, script.check_template, {'input': user_input},
                input_done_with=script.check_ok_sign,
                parse_keys=script.parse_vars,
                model=model, temperature=temperature)
        else:
            full_result = streaming_from_template(
                chat_box, script.template,
                {v: st.session_state[v] for v in script.template_vars} if script.template_vars else None,
                model=model, temperature=temperature
            )
        logging.debug(f'scrip id: {script.id}, chat result: {full_result}')
        # st.write(full_result)
        return model, temperature, full_result


    def debug_model2(model, temperature, script, variables, system_role, user_input):

        if script.check_template == '未填写！':
            full_result = from_template(script.template, variables, system_role, model, temperature)
        else:
            full_result = from_template(script.check_template, {'input': user_input}, None, model, temperature)
        logging.debug(f'scrip id: {script.id}, chat result: {full_result}')
        # st.write(full_result)
        return model, temperature, full_result


    add_vertical_space(2)
    col1, col2, col3 = st.columns([0.25, 0.25, 0.5])
    with col1:
        test_times = st.number_input('列数(一个模型测几遍)：', value=4, min_value=1, step=1)
    with col2:
        max_height = st.number_input('最大行高：', value=300, min_value=100, step=10)
    with col3:
        user_input = st.text_input('用户输入', placeholder=st.session_state.debug_script.input_placeholder)

    is_norm_prompt = True
    if st.session_state.debug_script.check_template == '未填写！':
        st.write('测试内容为 Prompt模版， 可改写')
        st.session_state.debug_script.template = st.text_area('修改模版内容', st.session_state.debug_script.template, height=200)
    else:
        st.write('测试内容为 检查用户输入的模版， 可改写')
        st.session_state.debug_script.check_template = st.text_area('修改检查模版内容', st.session_state.debug_script.check_template, height=200)
        is_norm_prompt = False
    if st.button('开始测试', type='primary', use_container_width=True):
        # col_num = len(st.session_state.debug_models) if len(st.session_state.debug_models) <= max_col_num else max_col_num
        # row_num = (len(st.session_state.debug_models) + col_num - 1) // col_num
        # cols = st.columns(col_num)

        # threads = []
        # # 创建并启动线程
        # for i in range(row_num):
        #     cols = st.columns(col_num)
        #     for j in range(col_num):
        #         index = i * col_num + j
        #         if index < len(st.session_state.debug_models):
        #             model, temperature = st.session_state.debug_models[index]
        #             thread = threading.Thread(
        #                 target=debug_model,
        #                 args=(model, temperature, debug_prompt, st.session_state.debug_script.check_template != '未填写！', cols[j]))
        #             add_script_run_ctx(thread)
        #             # threads.append(thread)
        #             thread.start()
        #
        # # 等待所有线程完成
        # for thread in threads:
        #     thread.join()

        # for i in range(row_num):
        #     cols = st.columns(col_num)
        #     for j, (model, temperature) in enumerate(st.session_state.debug_models[i * col_num: (i + 1) * col_num]):
        #         with cols[j]:
        #             st.write(f'模型：{model}， 温度：{temperature}')
        #
        #             # ========== chat_box 初始化 ==========
        #             chat_box = ChatBox(assistant_avatar=ICON_SIFU, session_key=str(uuid4()))
        #             chat_box.init_session()
        #             chat_box.output_messages()
        #
        #             script = st.session_state.debug_script
        #
        #             if script.check_template == '未填写！':
        #                 full_result = streaming_from_template(
        #                     chat_box, debug_prompt,
        #                     {v: st.session_state[v] for v in script.template_vars} if script.template_vars else None,
        #                     model=script.custom_model, temperature=script.temperature
        #                 )
        #             else:
        #                 # 通过 `检查模版` 输出AI回复
        #                 full_result = streaming_from_template(
        #                     chat_box, debug_prompt, {'input': user_input},
        #                     input_done_with=script.check_ok_sign,
        #                     parse_keys=script.parse_vars,
        #                     model=script.custom_model, temperature=script.temperature)
        #                 logging.debug(f'scrip id: {script.id}, chat result: {full_result}')

        # 初始化线程池
        executor = concurrent.futures.ThreadPoolExecutor()

        futures = []
        for model, temperature in st.session_state.debug_models:
            # 提交计算任务到线程池
            # future = executor.submit(debug_model, model, temperature, st.session_state.debug_script, st.session_state.system_role)
            for i in range(test_times):
                future = executor.submit(
                    debug_model2, model, temperature, st.session_state.debug_script,
                    {v: st.session_state[v] for v in st.session_state.debug_script.template_vars} if st.session_state.debug_script.template_vars else None,
                    st.session_state.system_role if 'system_role' in st.session_state else None,
                    user_input)
                futures.append(future)

        # 收集计算结果
        with st.spinner('正在输出，请稍后...'):
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # # 计算列数和行数
        # col_num = len(st.session_state.debug_models) if len(st.session_state.debug_models) <= max_col_num else max_col_num
        # row_num = (len(st.session_state.debug_models) + col_num - 1) // col_num

        # 根据收集的结果显示
        for i in range(len(st.session_state.debug_models)):
            cols = st.columns(test_times)
            for j in range(test_times):
                model, temperature, result = results[i * test_times + j]
                with cols[j]:
                    st.write(f'#### {model}， temp={temperature}')
                    st.write(result)
            st.write('-----')
