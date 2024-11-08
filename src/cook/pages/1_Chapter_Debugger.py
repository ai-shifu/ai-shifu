import logging
import time
from collections import defaultdict

import yaml
from yaml.loader import SafeLoader
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_chatbox import ChatBox, Image
from streamlit_extras.bottom_container import bottom
from langchain_core.messages import HumanMessage, AIMessage

from models.course import get_courses_by_user
from tools.lark import get_bitable_tables
from tools.utils import (
    ICON_SIFU,
    PromptTemplate,
    load_scripts,
    load_scripts_from_bitable,
    extract_variables,
    streaming_for_follow_up_ask,
    simulate_streaming,
    streaming_from_template,
    parse_vars_from_template,
    distribute_elements,
)
from models.script import Script, ScriptType, ScriptFormat, NextAction
from init import cfg


# ==================== Initialization ====================
# Set page title and icon
st.set_page_config(
    page_title="Chapter Debugger | Cook for AI-Shifu",
    page_icon="🧙‍♂️",  # 👨‍🏫
)
# The main title and subtitle on the page
"# Chapter Debugger ⌨️🧙‍♂️⌨️"  # 📚
st.caption(
    "📚 Loading chapter script to simulate user experience for linear debugging."
)


# ========== Debug init ==========
# Enable developer mode?
st.session_state.DEV_MODE = True if st.query_params.get("dev") else False
logging.info(f"DEV_MODE: {st.session_state.DEV_MODE}")

# ========== chat_box init ==========
chat_box = ChatBox(assistant_avatar=ICON_SIFU)
chat_box.init_session()
chat_box.output_messages()

# ========== session init ==========
# Initialization Progress ID
if "progress" not in st.session_state:
    st.session_state.progress = 0

# Record whether the script is output
if "script_has_output" not in st.session_state:
    st.session_state.script_has_output = set()

if "has_started" not in st.session_state:
    st.session_state.has_started = False

# if 'lark_app_token' not in st.session_state:
#     st.session_state.lark_app_token = ''

if "miss_vars" not in st.session_state:
    st.session_state.miss_vars = False

if "system_miss_vars" not in st.session_state:
    st.session_state.system_miss_vars = False

if "auto_continue" not in st.session_state:
    st.session_state.auto_continue = True

if "chat_history_list" not in st.session_state:
    st.session_state.chat_history_list = [HumanMessage("Let's start the lecture.")]

if "follow_up_history_count" not in st.session_state:
    st.session_state.follow_up_history_count = 0

if "has_follow_up_ask" not in st.session_state:
    st.session_state.has_follow_up_ask = False

if "user_follow_up_ask" not in st.session_state:
    st.session_state.user_follow_up_ask = ""

if "progress_follow_up_ask_counter" not in st.session_state:
    st.session_state.progress_follow_up_ask_counter = defaultdict(int)

# ======================================================

# ==================== Sidebar ====================
with st.sidebar:
    st.caption("After updating in Lark(Feishu), you need click to clear the cache.")
    if st.button("Clean all cache", use_container_width=True):
        st.cache_data.clear()

    # Debug of follow-up ask
    # st.write(st.session_state.chat_history_list)


# ==================== Main framework ====================
if not st.session_state.has_started:

    with open("auth_config.yml") as file:
        config = yaml.load(file, Loader=SafeLoader)

    # Pre-hashing all plain text passwords once
    # Hasher.hash_passwords(config['credentials'])

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
        config["pre-authorized"],
    )

    authenticator.login()

    if st.session_state["authentication_status"]:
        # authenticator.logout()
        # st.write(f'Welcome *{st.session_state["name"]}*')
        # st.title('Some content')

        courses = get_courses_by_user(st.session_state["username"])
        # courses = get_courses_by_user_from_sqlite('kenrick')
        if not courses:
            st.warning(
                " No courses available, please go to `My Account` to create a new course.。  ⬇️ ⬇️ ⬇️",
                icon="⚠️",
            )
            if st.button(
                "Go to `My Account`", type="primary", use_container_width=True
            ):
                st.switch_page("pages/100_My_Account.py")
            st.stop()

        col1, col2, col3 = st.columns(3)
        with col1:
            selected_course = st.selectbox(
                "Select Course:", (course.course_name for course in courses)
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
                    "Select Chapter:",
                    (
                        table.name
                        for table in tables
                        if not table.name.startswith("字典-")
                    ),
                )
                st.session_state.lark_table_id = next(
                    (table.table_id for table in tables if table.name == select_table),
                    None,
                )
                # Load script and system roles
                if "script_list" in st.session_state:
                    del st.session_state["script_list"]  # clear before load
                load_scripts(
                    st.session_state.lark_app_token, st.session_state.lark_table_id
                )

            with col3:
                select_script = st.selectbox(
                    "Starting position:", st.session_state.script_list
                )
                st.session_state.progress = st.session_state.script_list.index(
                    select_script
                )

        if select_script:
            st.text_area(
                "Script content", select_script.template, disabled=True, height=200
            )

        col1, col2, col3 = st.columns([3, 4, 5])
        with col1:
            st.session_state.auto_continue = st.toggle("Auto continue", True)
        with col2:
            supported_models = [model for model in cfg.SUPPORT_MODELS]
            model = st.selectbox(
                "Select LLM：",
                supported_models,
                index=cfg.SUPPORT_MODELS.index(cfg.DEFAULT_MODEL),
                label_visibility="collapsed",
            )
            cfg.set_default_model(model)
        with col3:
            if st.button("Start debugging", type="primary", use_container_width=True):
                st.session_state.has_started = True
                st.rerun()

    elif st.session_state["authentication_status"] is False:
        st.error("Username/password is incorrect")
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password")

# Directly start without developer mode, if in developer mode, wait for configuration to start.
# if not st.session_state.DEV_MODE or st.session_state.has_started:
else:

    # Get the total length of the script and stop at the end.
    if st.session_state.progress >= st.session_state.script_list_len:
        with bottom():
            st.write("")
        st.stop()

    if (
        "system_role_script" in st.session_state
        and "system_role" not in st.session_state
    ):
        system_needed_vars = extract_variables(
            st.session_state.system_role_script.template
        )
        if system_needed_vars:
            system_miss_vars = [
                var for var in system_needed_vars if var not in st.session_state
            ]
            if system_miss_vars:
                st.session_state.system_miss_vars = True
                with st.form("sys_miss_vars"):
                    "### Variables are needed in the system role template."
                    for var in system_miss_vars:
                        val = st.text_input(f"Input the value of  `{var}` ：")
                        if val != "":
                            st.session_state[var] = val

                    submitted = st.form_submit_button(
                        "Submit variables to continue",
                        type="primary",
                        use_container_width=True,
                    )
                    if submitted:
                        st.session_state.system_miss_vars = False
                        # time.sleep(5)
                        # st.rerun()
            else:
                st.session_state.system_miss_vars = False

        if not st.session_state.system_miss_vars:
            template = st.session_state.system_role_script.template
            variables = (
                {
                    v: st.session_state[v]
                    for v in st.session_state.system_role_script.template_vars
                }
                if st.session_state.system_role_script.template_vars
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
            st.session_state.system_role_id = st.session_state.system_role_script.id

    else:
        # According to the current progress ID, obtain the corresponding script.
        script: Script = st.session_state.script_list[st.session_state.progress]
        logging.debug(f"Current Script: \n{script}")
        # if st.session_state.DEV_MODE:
        #     show_current_script(script)

        needed_vars = extract_variables(script.template)
        # st.session_state
        if needed_vars:
            logging.debug("=== need vars")
            missing_vars = [var for var in needed_vars if var not in st.session_state]

            has_empty_val = False
            for var in needed_vars:
                if not st.session_state.get(var):
                    has_empty_val = True
                    break

            if missing_vars or has_empty_val:
                logging.debug("=== if missing_vars or has_empty_val")
                st.session_state.miss_vars = True

                # with st.form('missing_vars'):
                with st.expander("Now Script Template:", expanded=True):
                    st.text_area(
                        "Script content", script.template, disabled=True, height=300
                    )
                st.write(f"Need var: **{needed_vars}**,   missing: **{missing_vars}**")
                with st.form("missing_vars"):
                    for var in missing_vars:
                        val = st.text_input(f"Input the value of  `{var}` : ")
                        if val != "":
                            st.session_state[var] = val

                    submitted = st.form_submit_button(
                        "Submit variables to continue",
                        type="primary",
                        use_container_width=True,
                    )
                    if submitted:
                        st.session_state.miss_vars = False
                        # time.sleep(5)
                        # st.rerun()
            else:
                st.session_state.miss_vars = False

        # Can only proceed when there are no missing vars:
        if not st.session_state.miss_vars:

            # ========== Content Output Section ==========
            # If there are follow-up questions, answer them first.
            if st.session_state.has_follow_up_ask:
                chat_box.user_say(
                    st.session_state.user_follow_up_ask
                )  # Display user input information

                full_result = streaming_for_follow_up_ask(
                    chat_box,
                    st.session_state.user_follow_up_ask,
                    st.session_state.chat_history_list[
                        -st.session_state.follow_up_history_count :  # noqa E203
                    ],
                )

                # Add output to history list
                st.session_state.chat_history_list.append(
                    HumanMessage(st.session_state.user_follow_up_ask)
                )
                st.session_state.chat_history_list.append(AIMessage(full_result))

                if st.session_state.has_follow_up_ask:
                    script.btn_label = "Sure, let's continue the teaching~"

                st.session_state.has_follow_up_ask = False

            # If the script has not been output, then output it.
            elif script.id not in st.session_state.script_has_output:
                full_result = None

                # ===【固定剧本】：Simulated streaming output
                if script.type == ScriptType.FIXED:
                    if script.format == ScriptFormat.MARKDOWN:
                        logging.debug("=== Planning to simulate output")
                        full_result = simulate_streaming(
                            chat_box, script.template, script.template_vars
                        )
                    elif script.format == ScriptFormat.IMAGE:
                        chat_box.ai_say(Image(script.media_url))
                        full_result = script.media_url

                # == 【Prompt】：Submit the script content to LLM and get AI response output.
                elif script.type == ScriptType.PROMPT:
                    full_result = streaming_from_template(
                        chat_box,
                        script.template,
                        (
                            {v: st.session_state[v] for v in script.template_vars}
                            if script.template_vars
                            else None
                        ),
                        model=script.custom_model,
                        temperature=script.temperature,
                    )

                # Record the last output script ID to avoid duplicate output.
                st.session_state.script_has_output.add(script.id)
                logging.debug(f"script id: {script.id}, chat result: {full_result}")

                # Add output to history list
                if full_result:
                    st.session_state.chat_history_list.append(AIMessage(full_result))

            # ========== Processing【后续交互】 ==========
            # === Show input
            if script.next_action == NextAction.ShowInput:
                # Get user input
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # Display user input information
                    st.session_state.chat_history_list.append(
                        HumanMessage(user_input)
                    )  # Add output to history list

                    # Extract variables through `check template`（JSON mode）
                    is_ok = parse_vars_from_template(
                        chat_box,
                        script.check_template,
                        {"input": user_input},
                        parse_keys=script.parse_vars,
                        model=script.custom_model,
                        temperature=script.temperature,
                    )

                    # If executed ok, proceed to the next script.
                    if is_ok:
                        st.session_state.progress += 1
                        st.rerun()

            # === Show button
            elif script.next_action == NextAction.ShowBtn:

                def handle_button_click():
                    chat_box.user_say(script.btn_label)  # Show user input message
                    st.session_state.chat_history_list.append(
                        HumanMessage(script.btn_label)
                    )  # Add output to history list
                    st.session_state.progress += 1
                    st.session_state.has_follow_up_ask = False
                    st.rerun()

                if st.session_state.auto_continue:
                    handle_button_click()
                else:
                    with bottom():
                        if st.button(
                            script.btn_label, type="primary", use_container_width=True
                        ):
                            handle_button_click()

            # === Show button group
            elif script.next_action == NextAction.ShowBtnGroup:
                with bottom():
                    btns = distribute_elements(script.btn_group_cfg["btns"], 3, 2)
                    for row in btns:
                        st_cols = st.columns(len(row))
                        for i, btn in enumerate(row):
                            if st_cols[i].button(
                                btn["label"],
                                key=btn["value"],
                                type="primary",
                                use_container_width=True,
                            ):
                                # Get the value of the button clicked by the user
                                st.session_state[script.btn_group_cfg["var_name"]] = (
                                    btn["value"]
                                )
                                chat_box.user_say(
                                    btn["value"]
                                )  # Show user input message
                                st.session_state.chat_history_list.append(
                                    HumanMessage(btn["value"])
                                )  # Add output to history list
                                st.session_state.progress += 1
                                st.rerun()

            # === Jump Button
            elif script.next_action == NextAction.JumpBtn:
                if st.button(
                    script.btn_label, type="primary", use_container_width=True
                ):
                    # Get the value of the variable that needs to be judged.
                    var_value = st.session_state.get(script.btn_jump_cfg["var_name"])
                    # == If it is a silent jump
                    if script.btn_jump_cfg["jump_type"] == "silent":
                        # Find the sub-script to jump to
                        lark_table_id, lark_view_id = None, None
                        for jump_rule in script.btn_jump_cfg["jump_rule"]:
                            if var_value == jump_rule["value"]:
                                lark_table_id = jump_rule["lark_table_id"]
                                lark_view_id = jump_rule["lark_view_id"]

                        # If found, load it; otherwise, report an error.
                        if lark_table_id:
                            sub_script_list = load_scripts_from_bitable(
                                st.session_state.lark_app_token,
                                lark_table_id,
                                lark_view_id,
                            )
                            # Insert the sub-script into the original script.
                            st.session_state.script_list = (
                                st.session_state.script_list[
                                    : st.session_state.progress + 1
                                ]
                                + sub_script_list
                                + st.session_state.script_list[
                                    st.session_state.progress + 1 :  # noqa E203
                                ]
                            )
                            chat_box.user_say(
                                script.btn_label
                            )  # Show user input message
                            st.session_state.chat_history_list.append(
                                HumanMessage(script.btn_label)
                            )  # Add output to history list
                            # Update total script length
                            st.session_state.script_list_len = len(
                                st.session_state.script_list
                            )
                            # Update progress
                            st.session_state.progress += 1
                            # rerun
                            st.rerun()

                        else:
                            raise ValueError("No corresponding sub-script found")

            # === Show Pay QR Code
            elif script.next_action == NextAction.ShowPayQR:
                chat_box.ai_say("```Show pay QR code, simulate pay process```")
                st.session_state.progress += 1
                st.rerun()

            # === Input phone number
            elif script.next_action == NextAction.InputPhoneNum:
                # Get user input
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # Show user input message

                    # Do not take any action for now, proceed directly to the next step.
                    st.info(
                        "Do not take any action for now, proceed directly to the next step.",
                        icon="ℹ️",
                    )
                    time.sleep(1)
                    st.session_state.progress += 1
                    st.rerun()

            # === Input verification code
            elif script.next_action == NextAction.InputVerifyCode:
                # Get user input
                if user_input := st.chat_input(script.input_placeholder):
                    chat_box.user_say(user_input)  # Show user input message

                    # Do not take any action for now, proceed directly to the next step.
                    st.info(
                        "Do not take any action for now, proceed directly to the next step.",
                        icon="ℹ️",
                    )
                    time.sleep(1)
                    st.session_state.progress += 1
                    st.rerun()

            # === Show login/register
            elif script.next_action == NextAction.ShowLoginReg:
                chat_box.ai_say(
                    "```Show login/register dialog, simulate login/register process```"
                )
                st.session_state.progress += 1
                st.rerun()

            else:
                st.session_state.progress += 1
                st.rerun()

            with bottom():
                # follow_up_history_count = 0  # 0 Indicates all history
                col1, col2 = st.columns([1, 2])
                with col1:
                    history_count_options = [
                        "Use all history",
                        "Use 1 pair history",
                        "Use 2 pair history",
                        "Use 3 pair history",
                        "Use 4 pair history",
                        "Use 5 pair history",
                        "Use 10 pair history",
                        "Use 15 pair history",
                        "Use 20 pair history",
                    ]
                    select_option = st.selectbox(
                        "Number of usage history records:",
                        history_count_options,
                        label_visibility="collapsed",
                    )
                    st.session_state.follow_up_history_count = (
                        history_count_options.index(select_option) * 2
                    )
                    # st.write(st.session_state.follow_up_history_count)

                with col2:
                    # Get user input
                    if user_input := st.chat_input("Enter follow-up ask"):
                        st.session_state.user_follow_up_ask = user_input
                        st.session_state.has_follow_up_ask = True
                        st.rerun()
