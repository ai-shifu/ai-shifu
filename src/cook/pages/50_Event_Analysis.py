from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st


from models.script import ScriptType
from tools.auth import login
from tools.umami_event_analysis import (
    get_trail_script_count,
    get_chapter_visit_user_by_start_with,
    get_event_num_of_user_and_times,
)
from tools.utils import load_scripts

st.set_page_config(page_title="Event Analysis", page_icon="🧙‍♂️", layout="wide")

# 页面内的大标题小标题
"# 埋点事件分析器 📊📈📉"
st.caption("")

with login():

    tab1, tab2, tab10 = st.tabs(["体验课漏斗", "章节漏斗", "其他"])

    with tab1:

        system_role_script = load_scripts()
        if st.session_state.script_list[0].type == ScriptType.SYSTEM:
            system_role_script = st.session_state.script_list.pop(0)

        # print(st.session_state.script_list[0])

        df = pd.DataFrame(columns=["剧本简述", "数量"])

        for script in st.session_state.script_list:
            df.loc[len(df)] = [script.desc, 0]

        umami_event_count = get_trail_script_count()
        for index, row in umami_event_count.iterrows():
            for i, script in enumerate(st.session_state.script_list):
                if script.desc == row["string_value"]:
                    df.loc[i, "数量"] = row["count(*)"]
        print(umami_event_count)
        print(df)

        script_num = len(df)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 绘制漏斗图
        fig = px.funnel(
            df,
            x="数量",
            y="剧本简述",
            title=f"体验课剧本漏斗 ({current_time})",
            height=script_num * 50,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 计算下降比例
        df["下降比例"] = df["数量"].pct_change().fillna(0)
        df.loc[0, "下降比例"] = 0

        # 绘制图表
        fig = px.line(
            df,
            x="剧本简述",
            y="下降比例",
            title=f"剧本间下降比例 ({current_time})",
            labels={"剧本简述": "剧本简述", "下降比例": "下降比例"},
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:

        chapter_from = []
        for i in range(8):
            chapter_from.append(
                get_chapter_visit_user_by_start_with(f"{i:02}", "from")[
                    "string_value"
                ].to_list()
            )

        chapter_arrivals = []
        for i in range(8):
            chapter_arrivals.append(
                get_chapter_visit_user_by_start_with(f"{i:02}")[
                    "string_value"
                ].to_list()
            )

        df = pd.DataFrame(columns=["章节名称", "到达人数"])
        df.loc[0] = ["00-了解 AI 编程这回事", len(chapter_arrivals[0])]
        df.loc[1] = ["01- 如何向 AI 提项目需求？", len(chapter_arrivals[1])]
        df.loc[2] = ["02- 如何通过 AI 学 python", len(chapter_arrivals[2])]
        df.loc[3] = ["03- AI 编程的初体验", len(chapter_arrivals[3])]
        df.loc[4] = ["04- 借助 AI 来读懂代码", len(chapter_arrivals[4])]
        df.loc[5] = ["05- 让 AI 写的代码可用", len(chapter_arrivals[5])]
        df.loc[6] = ["06- 用 AI 处理运行错误", len(chapter_arrivals[6])]
        df.loc[7] = ["07- 用 AI 完成一个程序", len(chapter_arrivals[7])]

        script_num = len(df)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 绘制漏斗图
        fig = px.funnel(
            df,
            x="到达人数",
            y="章节名称",
            title=f"章节漏斗 ({current_time})",
            height=script_num * 60,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 计算下降比例
        df["下降比例"] = df["到达人数"].pct_change().fillna(0)
        df.loc[0, "下降比例"] = 0

        # 绘制图表
        fig = px.line(
            df,
            x="章节名称",
            y="下降比例",
            title=f"章节间下降比例 ({current_time})",
            labels={"章节名称": "章节名称", "下降比例": "下降比例"},
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        "### 章节到达用户"
        chapter_tabs = st.tabs(df["章节名称"].to_list())
        for i, tab in enumerate(chapter_tabs):
            with tab:
                st.write(f"总人数：{len(chapter_arrivals[i])}")
                for j in chapter_arrivals[i]:
                    st.write(j)

    with tab10:
        user_count, times_count = get_event_num_of_user_and_times("nav_top_logo")
        f"## nav_top_logo 人数：{user_count} 次数：{times_count}"

        user_count, times_count = get_event_num_of_user_and_times("nav_bottom_beian")
        f"## nav_bottom_beian 人数：{user_count} 次数：{times_count}"

        user_count, times_count = get_event_num_of_user_and_times("nav_bottom_skin")
        f"## nav_bottom_skin 人数：{user_count} 次数：{times_count}"

        user_count, times_count = get_event_num_of_user_and_times("nav_bottom_setting")
        f"## nav_bottom_setting 人数：{user_count} 次数：{times_count}"

        user_count, times_count = get_event_num_of_user_and_times("nav_top_expand")
        f"## nav_top_expand 人数：{user_count} 次数：{times_count}"

        user_count, times_count = get_event_num_of_user_and_times("nav_top_collapse")
        f"## nav_top_collapse 人数：{user_count} 次数：{times_count}"
