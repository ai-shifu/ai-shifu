import pandas
import streamlit as st
import streamlit_authenticator as stauth
from streamlit_extras.add_vertical_space import add_vertical_space
from pandas import DataFrame, Series
import yaml
from yaml.loader import SafeLoader

from models.course import *
from tools.auth import login


@st.dialog('✏️ 修改 课程')
def edit_course(course: Series, user_name):
    with st.form('edit_row'):
        course_name = st.text_input('课程名称', value=course['course_name'])
        lark_app_id = st.text_input('飞书 App ID', value=course['lark_app_token'])
        if st.form_submit_button('更新', type='primary', use_container_width=True):
            update_course_by_course_id(int(course.name), user_name, course_name, lark_app_id)
            st.rerun()


@st.dialog('❌ 删除 课程')
def delete_course(course: Series):
    with st.form('delete_row'):
        st.text_input('课程名称', course['course_name'], disabled=True)
        st.text_input('飞书 App ID', course['lark_app_token'], disabled=True)
        if st.form_submit_button(f'确认删除 {course["course_name"]}', type='primary', use_container_width=True):
            del_course_by_course_id(int(course.name))
            st.rerun()


# 需要登录
authenticator, config = login()
if authenticator is not False:

    if st.session_state["authentication_status"]:
        user_name = st.session_state["username"]
        # user_name = 'zhangsan'
        st.write('# 个人帐户管理 🧑‍💼🔐🧑‍💼')
        st.caption(f'欢迎 *{user_name}*')
        '-----'
        '## 课程信息'
        df_courses = DataFrame([chapter.__dict__ for chapter in get_courses_by_user_from_sqlite(user_name)])
        if df_courses.empty:
            '##### ⬇️ 暂无课程，请新建 ⬇️'
        else:
            df_courses = df_courses[['course_id', 'course_name', 'lark_app_token']]
            df_courses.set_index('course_id', inplace=True)
            event = st.dataframe(
                df_courses,
                column_config={
                    'course_name': '课程名称',
                    'lark_app_token': '飞书 App ID'
                },
                use_container_width=True,
                hide_index=True,
                on_select='rerun',
                selection_mode='single-row',
                key='课程信息'
            )

            if event.selection['rows']:
                selected_course: pandas.Series = df_courses.iloc[event.selection['rows'][0]]

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f'✏️ 修改 {selected_course["course_name"]}', use_container_width=True):
                        edit_course(selected_course, user_name)

                with col2:
                    if st.button(f'❌ 删除 {selected_course["course_name"]}', use_container_width=True):
                        delete_course(selected_course)


        # 添加 课程
        with st.expander('➕ 添加 课程'):
            with st.form('add_row'):
                course_name = st.text_input('课程名称', placeholder='建议和飞书文档中的课程名称保持一致')
                lark_app_id = st.text_input(
                    '飞书 App ID',
                    placeholder='飞书文档地址栏中 https://zhentouai.feishu.cn/base/{这里的一串字符}?table=xxx...'
                )
                if st.form_submit_button('添加', type='primary', use_container_width=True):
                    insert_course(user_name, course_name, lark_app_id)
                    st.rerun()
            pass


        add_vertical_space(2)



        '-----'
        '## 帐户信息'

        # 修改用户信息
        with st.expander('📝 修改用户信息'):
            if st.session_state["authentication_status"]:
                try:
                    if authenticator.update_user_details(
                        username=st.session_state["username"],
                        fields={
                            'Form name': '更新用户信息',
                            'Field': '要更新的字段',
                            'Name': '用户名',
                            'Email': '邮箱',
                            'New value': '更新为',
                            'Update': '更新'
                        }
                    ):
                        with open('auth_config.yml', 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success('用户信息更新成功')
                except Exception as e:
                    st.error(e)

        # add_vertical_space(1)

        # 重置密码
        with st.expander('🔑 重置密码'):
            try:
                if authenticator.reset_password(
                    username=st.session_state["username"],
                    fields={
                        'Form name': '重置密码',
                        'Current password': '当前密码',
                        'New password': '新密码',
                        'Repeat password': '重复新密码',
                        'Reset': '重置'
                    }
                ):
                    with open('auth_config.yml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    st.success('密码重置成功')
            except Exception as e:
                st.error(e)

        add_vertical_space(1)

        '-----'
        # 退出登录
        if st.button('退出登录', use_container_width=True):
            authenticator.logout(location='unrendered')
            st.session_state.is_login_welcome = False


    elif st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning('Please enter your username and password')
