import concurrent.futures
import logging

from streamlit_extras.add_vertical_space import add_vertical_space

from models.course import get_courses_by_user
from tools.auth import login
from tools.lark import get_bitable_tables, update_bitable_record
from tools.utils import (
    st,
    from_template,
    count_lines,
    extract_variables,
    load_scripts_and_system_role,
)
from models.script import Script, ScriptType
from init import cfg, get_default_temperature, load_dotenv, find_dotenv


_ = load_dotenv(find_dotenv())


# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="Script Debugger | Cook for AI-Shifu",
    page_icon="🧙‍♂️",
    initial_sidebar_state="collapsed",
    layout="wide",
    menu_items={
        "Get Help": "https://www.extremelycoolapp.com/help",
        "Report a bug": "https://www.extremelycoolapp.com/bug",
        "About": "# This is a header. This is an *extremely* cool app!",
    },
)

# 页面内的大标题小标题
"# 单条剧本调试器 🐞📜🐞"
st.caption("📚 可使用多个不同模型同时多次输出，以便比较不同模型的输出结果和稳定性。")

# ==================== SS初始化 ====================
if "is_single_script_loaded" not in st.session_state:
    st.session_state.is_single_script_loaded = False

if "miss_vars" not in st.session_state:
    st.session_state.miss_vars = False

if "st.session_state.debugger_user_input" not in st.session_state:
    st.session_state.debugger_user_input = None

# ==================== Sidebar ====================
with st.sidebar:
    st.caption("飞书中更新后可以点击清除缓存")
    if st.button("Clean all cache", use_container_width=True):
        st.cache_data.clear()


# ==================== Functions ====================
def debug_model(model, temperature, script, variables, system_role, user_input):
    print(
        f"=== debug_model: {model}, {temperature}, {script}, {variables}, {system_role}, {user_input}"
    )

    if script.check_template == "未填写！":
        full_result = from_template(
            script.template, variables, system_role, model, temperature
        )
    else:
        full_result = from_template(
            script.check_template, {"input": user_input}, None, model, temperature
        )
    logging.debug(f"scrip id: {script.id}, chat result: {full_result}")
    # st.write(full_result)
    return model, temperature, full_result


# ==================== 主体框架 ====================
# 需要登录
with login():

    # 初始化要调试的模型列表
    if "debug_models" not in st.session_state:
        st.session_state.debug_models = [(cfg.DEFAULT_MODEL, cfg.DEFAULT_TMP)]

    # 初始化要调试的单条剧本
    if "debug_script" not in st.session_state:
        st.session_state.debug_script = None

    # =========================================================
    # ===== 配置 要调试的模型
    "## Step1: 添加参与测试的模型"
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        models = []
        supported_models_without_default = [
            model for model in cfg.SUPPORT_MODELS if model != cfg.DEFAULT_MODEL
        ]
        model = st.selectbox(
            "选择模型：",
            supported_models_without_default,
            index=cfg.SUPPORT_MODELS.index(cfg.DEFAULT_MODEL),
        )
        temperature = get_default_temperature(model)
        temperature = st.number_input("设定温度：", value=temperature)
        if st.button("添加测试模型 -->", use_container_width=True):
            if (model, temperature) not in st.session_state.debug_models:
                st.session_state.debug_models.append((model, temperature))
    with col2:
        st.caption("参测模型列表（表格左侧复选框勾选后可删除）：")
        # add_vertical_space(1)
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

        select_rows: list = df_models.selection["rows"]
        if select_rows:
            # .write(f'选中的行：{select_rows}')
            if st.button(f"删除选中行：{select_rows}", use_container_width=True):
                select_rows.sort(reverse=True)
                for row in select_rows:
                    if row < len(st.session_state.debug_models):
                        st.session_state.debug_models.pop(row)
                    else:
                        st.error(f"无效的行索引: {row}")
                st.rerun()

    # =========================================================
    # ===== 加载 指定单条剧本
    add_vertical_space(2)
    "-----"
    "## Step2: 指定要测试的单条剧本"
    courses = get_courses_by_user(st.session_state["username"])
    if not courses:
        st.warning(" 暂无课程，请前往我的账户新建课程。  ⬇️ ⬇️ ⬇️", icon="⚠️")
        if st.button("前往我的账户", type="primary", use_container_width=True):
            st.switch_page("pages/100_My_Account.py")
        st.stop()

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_course = st.selectbox(
            "选择课程:", (course.course_name for course in courses)
        )

    if selected_course:
        st.session_state.lark_app_token = next(
            (
                course.lark_app_token
                for course in courses
                if course.course_name == selected_course
            ),
            None,
        )
        tables = get_bitable_tables(st.session_state.lark_app_token)

        with col2:
            select_table = st.selectbox(
                "选择章节:",
                (table.name for table in tables if not table.name.startswith("字典-")),
            )
            st.session_state.lark_table_id = next(
                (table.table_id for table in tables if table.name == select_table), None
            )
            # 加载剧本及系统角色
            if "script_list" in st.session_state:
                del st.session_state["script_list"]  # clear before load
            load_scripts_and_system_role(
                st.session_state.lark_app_token, st.session_state.lark_table_id
            )

        with col3:
            select_script = st.selectbox("开始位置:", st.session_state.script_list)
            st.session_state.progress = st.session_state.script_list.index(
                select_script
            )

    col1, col2 = st.columns([0.3, 0.7], gap="small")
    with col1:
        if st.button("刷新整个课程", use_container_width=True):
            st.cache_data.clear()
    with col2:
        if st.button("加载指定的单条剧本", type="primary", use_container_width=True):
            # 加载剧本及系统角色
            # load_scripts_and_system_role(cfg.LARK_APP_TOKEN, chapter.lark_table_id, chapter.lark_view_id)
            # progress += 1 if 'system_role' not in st.session_state else 0
            # st.session_state.progress = progress
            logging.debug(f"从 {st.session_state.progress} 开始剧本")
            script: Script = st.session_state.script_list[st.session_state.progress]
            st.session_state.debug_script = script
            st.session_state.is_single_script_loaded = True
            # st.write(f'app_token: {st.session_state.lark_app_token}')
            # st.write(f'table_id: {st.session_state.lark_table_id}')
            # st.write(f'record_id: {script.id}')

    # =========================================================
    if st.session_state.is_single_script_loaded:
        add_vertical_space(1)
        "### 剧本详情"
        col1, col2 = st.columns(2)
        with col1:
            if "system_role" in st.session_state:
                with st.expander("系统角色：", expanded=True):
                    st.session_state.system_role = st.text_area(
                        "系统角色",
                        st.session_state.system_role,
                        height=count_lines(st.session_state.system_role)[1] * 25,
                        label_visibility="collapsed",
                    )
                    if st.button("将系统角色更新至飞书", use_container_width=True):
                        if update_bitable_record(
                            st.session_state.lark_app_token,
                            st.session_state.lark_table_id,
                            st.session_state.system_role_id,
                            "模版内容",
                            st.session_state.system_role,
                        ):
                            st.success("更新成功！")
                system_role_needed_vars = extract_variables(
                    st.session_state.system_role
                )
            else:
                st.warning("未加载系统角色！")

            with st.expander(f"[{select_script}] 剧本内容", expanded=True):
                st.session_state.debug_script.template = st.text_area(
                    "剧本详情",
                    st.session_state.debug_script.template,
                    height=count_lines(st.session_state.debug_script.template)[1] * 25,
                    label_visibility="collapsed",
                )
                if st.button("将剧本内容更新至飞书", use_container_width=True):
                    if update_bitable_record(
                        st.session_state.lark_app_token,
                        st.session_state.lark_table_id,
                        st.session_state.debug_script.id,
                        "模版内容",
                        st.session_state.debug_script.template,
                    ):
                        st.success("更新成功！")

        with col2:

            needed_vars = (
                extract_variables(st.session_state.debug_script.template)
                + system_role_needed_vars
            )
            needed_vars = list(set(needed_vars))
            if needed_vars:
                "#### 出现变量"
                st.write(f"**{needed_vars}**")

                has_value = False
                for var in needed_vars:
                    if st.session_state.get(var):
                        st.write(f"已有： **{var}** = {st.session_state[var]}")
                        has_value = True
                if has_value:
                    st.write("⬆️刷新页面后可清空变量⬆️")

                missing_vars = [
                    var for var in needed_vars if var not in st.session_state
                ]
                # missing_vars = list(set(missing_vars))

                has_empty_val = False
                for var in needed_vars:
                    if not st.session_state.get(var):
                        has_empty_val = True
                        break

                if missing_vars or has_empty_val:
                    "#### 补全变量值"
                    logging.debug("=== if missing_vars or has_empty_val")
                    st.session_state.miss_vars = True

                    # st.write(f'需要变量: **{needed_vars}**,   缺失: **{missing_vars}**')
                    for var in missing_vars:
                        val = st.text_input(f"输入 {var} 的值：")
                        if val != "":
                            st.session_state[var] = val

                else:
                    st.session_state.miss_vars = False

        if (
            st.session_state.debug_script.type == ScriptType.FIXED
            and st.session_state.debug_script.check_template == "未填写！"
        ):
            st.warning("该剧本为固定剧本，且没有用户输入需要检查，不需要测试！")
        else:
            # edited_template = st.text_area('模版内容', script.template, height=200)
            # st.write(f"模版内容共计 {len(edited_template)} 个字符")
            if st.session_state.debug_script.check_template != "未填写！":
                "-----"
                "#### 需要用户输入"
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.debug_script.check_template = st.text_area(
                        "检查模版内容",
                        st.session_state.debug_script.check_template,
                        height=count_lines(
                            st.session_state.debug_script.check_template
                        )[1]
                        * 25,
                    )
                    if st.button("将检查模版内容更新至飞书", use_container_width=True):
                        if update_bitable_record(
                            st.session_state.lark_app_token,
                            st.session_state.lark_table_id,
                            st.session_state.debug_script.id,
                            "检查模版内容",
                            st.session_state.debug_script.check_template,
                        ):
                            st.success("更新成功！")
                with col2:
                    st.session_state.debugger_user_input = st.text_input(
                        "用户输入",
                        placeholder=st.session_state.debug_script.input_placeholder,
                    )

            # =========================================================
            # ===== 开始测试

            add_vertical_space(2)
            col1, col2 = st.columns(2)
            with col1:
                test_times = st.number_input(
                    "列数(一个模型测几遍)：", value=3, min_value=1, step=1
                )
            with col2:
                max_height = st.number_input(
                    "最大行高：", value=300, min_value=100, step=100
                )

            if st.button("开始测试", type="primary", use_container_width=True):
                print("=== 开始测试")

                # 初始化线程池
                executor = concurrent.futures.ThreadPoolExecutor()

                futures = []
                for model, temperature in st.session_state.debug_models:
                    for _ in range(test_times):
                        future = executor.submit(
                            debug_model,
                            model,
                            temperature,
                            st.session_state.debug_script,
                            (
                                {
                                    v: st.session_state[v]
                                    for v in st.session_state.debug_script.template_vars
                                }
                                if st.session_state.debug_script.template_vars
                                else None
                            ),
                            (
                                st.session_state.system_role
                                if "system_role" in st.session_state
                                else None
                            ),
                            st.session_state.debugger_user_input,
                        )
                        futures.append(future)

                # 收集计算结果
                with st.spinner("正在输出，请稍后..."):
                    results = [
                        future.result()
                        for future in concurrent.futures.as_completed(futures)
                    ]

                # # 计算列数和行数
                # col_num = len(st.session_state.debug_models) if len(st.session_state.debug_models) <= max_col_num else max_col_num
                # row_num = (len(st.session_state.debug_models) + col_num - 1) // col_num

                # 根据收集的结果显示
                for i in range(len(st.session_state.debug_models)):
                    cols = st.columns(test_times)
                    for j in range(test_times):
                        model, temperature, result = results[i * test_times + j]
                        with cols[j]:
                            st.write(f"#### {model}， temp={temperature}")
                            st.write(result)
                    st.write("-----")
