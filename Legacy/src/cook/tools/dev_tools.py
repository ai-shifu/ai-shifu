import streamlit as st


def show_current_script(script):
    with st.sidebar:
        st.write(f"当前剧本ID：{script.id}")
        with st.expander("查看剧本内容", expanded=True):
            st.write(script)
