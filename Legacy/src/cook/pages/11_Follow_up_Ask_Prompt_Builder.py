import logging

import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate

from init import cfg, load_llm, get_default_temperature
from models.chapter import load_chapters_from_api
from models.chapters_follow_up_ask_prompt import (
    update_ask_info_from_api,
    update_follow_up_ask_prompt_template,
)
from models.course import get_courses_by_user
from tools.auth import login
from tools.lark import get_bitable_tables
from tools.utils import count_lines, load_scripts

# ==================== Initialization ====================
# Set page title and icon
st.set_page_config(
    page_title="Follow-up Ask Prompt Builder | Cook for AI-Shifu",
    page_icon="🧙‍♂️",  # 👨‍🏫
)

# The main title and subtitle on the page
"# Follow-up Ask Prompt Builder 📝🛠️"
st.caption("Help build follow-up ask prompt templates for each chapter")


STSS = st.session_state

if "prompt_summarize_chapter" not in STSS:
    STSS.prompt_summarize_chapter = """# 你需要总结AI个性化教学课程 `{course_name}` 中某个章节的主要内容和教学要点。

当前要整理的章节是： `{chapter_name}`

整理总结后输出内容格式如下（摘要内容在200字以内；教学要点总结不要超过5条）：
```
### 章节 `xxx`：

#### 章节 `xxx` 的摘要：
【一段文本概述章节内容】

#### 章节 `xxx` 的教学要点有：
1. 【要点1】
2. 【要点2】
3. 【要点3】
...
```

该章节中的具体AI教学剧本内容如下：
{scripts_content}

"""

if "prompt_follow_up_ask" not in STSS:
    STSS.prompt_follow_up_ask = """# 现在学员在学习上述教学内容时，产生了一些疑问，你需要恰当的回答学员的追问。

**你就是老师本人，不要打招呼，直接用第一人称回答！**

如果学员的追问内容与当前章节教学内容有关，请优先结合当前章节中已经输出的内容进行回答。

如果学员的追问内容与当前章节教学内容关系不大，但与该课程的其他章节有关，你可以简要回答并友好的告知学员稍安勿躁，后续xx章节有涉及学员追问问题的详细教学内容。

如果学员的追问内容与课程教学内容无关，但与教学平台有关（平台使用问题；售卖、订单、退费等；账号、密码、登录等），请耐心的告知学员通过「哎师傅-AI学习社区」服务号找到我们进行相应的解决。

如果学员的追问内容与课程教学内容无关，也与教学平台无关，请友好的回绝学员的追问，并请学员专注在该课程内容的学习上。


学员的追问是：
`{input}`
"""

if "chapters_summary" not in STSS:
    STSS.chapters_summary = {}


@st.fragment
def show_and_update_summary(table, selected_course, model):
    try:
        if table.name.startswith("字典-"):
            return

        load_scripts(st.session_state.lark_app_token, table.table_id)

        scripts_content = ""
        for index, script in enumerate(st.session_state.script_list):
            scripts_content += f"#### 第{index}小节: {script.desc}:\n"
            scripts_content += script.template + "\n\n\n"

        variables = {
            "course_name": selected_course,
            "chapter_name": table.name,
            "scripts_content": scripts_content,
        }

        llm = load_llm(model)
        prompt = PromptTemplate(
            input_variables=list(variables.keys()),
            template=STSS.prompt_summarize_chapter,
        )
        prompt = prompt.format(**variables)

        with st.expander(f"Chapter `{table.name}` Summary:"):
            if (
                table.name not in STSS.chapters_summary
                or STSS.chapters_summary[table.name] is None
            ):
                with st.spinner(f"Chapter `{table.name}` is summarizing..."):
                    response = llm.invoke([HumanMessage(prompt)])
                    STSS.chapters_summary[table.name] = response.content
                    print(f"AI Generated Summary: {response.content}")

            STSS.chapters_summary[table.name] = st.text_area(
                f"Chapter `{table.name}` Summary:",
                value=STSS.chapters_summary[table.name],
                height=count_lines(STSS.chapters_summary[table.name], 40)[1] * 26,
                label_visibility="collapsed",
            )

        del st.session_state["script_list"]  # clear before next iteration
    except Exception as e:
        st.error(f"Error occurred when summarizing chapter {table.name}: \n\n{e}")
        print(f"Error occurred when summarizing chapter {table.name}: \n\n{e}")
        logging.error(f"Error occurred when summarizing chapter {table.name}: \n\n{e}")
        st.stop()


with login():
    courses = get_courses_by_user(st.session_state["username"])
    if not courses:
        st.warning(
            " No courses available, please go to `My Account` to create a new course.。  ⬇️ ⬇️ ⬇️",
            icon="⚠️",
        )
        if st.button("Go to `My Account`", type="primary", use_container_width=True):
            st.switch_page("pages/100_My_Account.py")
        st.stop()

    with st.expander("The beginning of the **Follow-up Ask Prompt Template**:"):
        STSS.prompt_follow_up_ask = st.text_area(
            "Please KEEP the variable name for follow-up ask as `input`:",
            STSS.prompt_follow_up_ask,
            height=500,
        )

    with st.expander("**Summary Prompt Template**:"):
        STSS.prompt_summarize_chapter = st.text_area(
            "Please KEEP the variable names for `course_name`, `chapter_name` and `scripts_content`:",
            STSS.prompt_summarize_chapter,
            height=500,
        )

    """
    > After clicking the generate button below,
    the summary for each chapter will be generated using the **Summary Prompt Template** above.
    >
    > Then, for each chapter, the **Follow-up Ask Prompt Template** above will be used as the beginning,
    followed by the current chapter summary and other chapter summaries.
    """

    add_vertical_space(1)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        selected_course = st.selectbox(
            "Select Course:", (course.course_name for course in courses)
        )
        with st.spinner("Loading bittable..."):
            st.session_state.lark_app_token = next(
                (
                    course.lark_app_token
                    for course in courses
                    if course.course_name == selected_course
                ),
                None,
            )

            STSS.updated_chapters = load_chapters_from_api(
                st.session_state.lark_app_token
            )[0]
            tables = get_bitable_tables(st.session_state.lark_app_token)
            tables = [
                table
                for table in tables
                if any(
                    chapter.lark_table_id == table.table_id
                    for chapter in STSS.updated_chapters
                )
            ]
            print(tables)
    with col2:
        model = st.selectbox(
            "Select Model (only for summarize):",
            cfg.SUPPORT_MODELS,
            index=cfg.SUPPORT_MODELS.index("deepseek-chat"),
        )
    with col3:
        temperature = get_default_temperature(model)
        temperature = st.number_input(
            "Temperature:", value=temperature, min_value=0.0, max_value=2.0, step=0.01
        )

    if st.button(
        "Generate all chapters follow-up ask prompt template",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Generating chapters summary..."):
            for table in tables:
                show_and_update_summary(table, selected_course, model)

        st.write(
            "Chapter summary completed, please choose a model for follow-up ask and start update"
        )
        with st.sidebar:
            st.write(STSS.chapters_summary)

    st.caption(
        """
    Due to the large amount of script content, the generation process may take some time.
    Please be patient.

    For the same reason, some models with a context length of 6K/8K may report errors due to
    context length limitations when summarizing.
    so we recommended models are: `gpt-4o`、`qwen2-72b`、`deepseek`
    """
    )

    add_vertical_space(2)

    if STSS.chapters_summary != {}:
        col1, col2 = st.columns([1, 2])
        with col1:
            STSS.ask_model = st.selectbox(
                "Select Model for follow-up ask):",
                cfg.SUPPORT_MODELS,
                index=cfg.SUPPORT_MODELS.index("qwen2-72b-instruct"),
                label_visibility="collapsed",
            )
        with col2:
            if st.button(
                "Update all chapters follow-up ask prompt template",
                use_container_width=True,
                type="primary",
            ):
                with st.sidebar:
                    st.write(STSS.chapters_summary)

                for table in tables:
                    try:
                        if table.name.startswith("字典-"):
                            continue

                        STSS.prompt_follow_up_ask += "\n"
                        full_summary = (
                            "## 当前章节的内容是：\n\n"
                            + STSS.chapters_summary[table.name]
                            + "\n\n## 课程其他章节的内容是：\n\n"
                        )

                        for chapter_name, summary in STSS.chapters_summary.items():
                            if chapter_name != table.name:
                                full_summary += summary + "\n\n"

                        update_follow_up_ask_prompt_template(
                            st.session_state.lark_app_token,
                            table.table_id,
                            STSS.prompt_follow_up_ask + full_summary,
                        )

                        lesson_id = next(
                            (
                                chapter.lesson_id
                                for chapter in STSS.updated_chapters
                                if chapter.lark_table_id == table.table_id
                            ),
                            None,
                        )
                        if lesson_id:
                            update_ask_info_from_api(
                                lesson_id=lesson_id,
                                lesson_ask_prompt=STSS.prompt_follow_up_ask
                                + full_summary,
                                lesson_summary=full_summary,
                                lesson_ask_model=STSS.ask_model,
                            )
                            st.success(
                                f"Already update '{table.name}' Follow-up Ask Prompt Template"
                            )
                        else:
                            st.warning(f"Can't find '{table.name}' lesson_id")
                    except Exception as e:
                        st.error(
                            f"Error occurred when splice Follow-up Ask Prompt Template for chapter {table.name}: \n{e}"
                        )
                        print(
                            f"Error occurred when splice Follow-up Ask Prompt Template for chapter {table.name}: \n{e}"
                        )
                        logging.error(
                            f"Error occurred when splice Follow-up Ask Prompt Template for chapter {table.name}: \n{e}"
                        )
                        st.stop()

                st.success(
                    "All chapters Follow-up Ask Prompt Templates have been generated and updated successfully."
                )
