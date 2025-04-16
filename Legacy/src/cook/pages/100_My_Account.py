import pandas
import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space
from pandas import DataFrame, Series
import yaml

from models.course import (
    update_course_by_course_id,
    del_course_by_course_id,
    get_courses_by_user,
    insert_course,
)
from tools.auth import login


st.set_page_config(
    page_title="My Account | Cook for AI-Shifu",
    page_icon="🔐",
)


@st.dialog("✏️ Update Course")
def edit_course(course: Series, user_name):
    with st.form("edit_row"):
        course_name = st.text_input("Course Name", value=course["course_name"])
        lark_app_id = st.text_input("Lark App ID", value=course["lark_app_token"])
        if st.form_submit_button(
            "Confirm Update", type="primary", use_container_width=True
        ):
            update_course_by_course_id(
                int(course.name), user_name, course_name, lark_app_id
            )
            st.rerun()


@st.dialog("❌ Delete Course")
def delete_course(course: Series):
    with st.form("delete_row"):
        st.text_input("Course Name", course["course_name"], disabled=True)
        st.text_input("Lark App ID", course["lark_app_token"], disabled=True)
        if st.form_submit_button(
            f'Confirm Delete {course["course_name"]}',
            type="primary",
            use_container_width=True,
        ):
            del_course_by_course_id(int(course.name))
            st.rerun()


# Need login
with login() as (authenticator, config):

    if st.session_state["authentication_status"]:
        user_name = st.session_state["username"]
        # user_name = 'zhangsan'
        st.write("# Account Management 🧑‍💼🔐🧑‍💼")
        st.caption(f"Welcome *{user_name}*")
        "-----"
        "## Course List"
        st.caption(
            "☑️ You can check the checkbox in front of the row to modify or delete a piece of data."
        )
        df_courses = DataFrame(
            [chapter.__dict__ for chapter in get_courses_by_user(user_name)]
        )
        if df_courses.empty:
            "##### ⬇️ No courses available, please create new ones. ⬇️"
        else:
            df_courses = df_courses[["id", "course_name", "lark_app_token"]]
            df_courses.set_index("id", inplace=True)
            event = st.dataframe(
                df_courses,
                column_config={
                    "course_name": "Course Name",
                    "lark_app_token": "Lark App ID",
                },
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="Course Information",
            )

            if event.selection["rows"]:
                selected_course: pandas.Series = df_courses.iloc[
                    event.selection["rows"][0]
                ]

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(
                        f'✏️ Edit: {selected_course["course_name"]}',
                        use_container_width=True,
                    ):
                        edit_course(selected_course, user_name)

                with col2:
                    if st.button(
                        f'❌ Delete: {selected_course["course_name"]}',
                        use_container_width=True,
                    ):
                        delete_course(selected_course)

        # Add Course
        with st.expander("➕ Add Course"):
            with st.form("add_row"):
                course_name = st.text_input(
                    "Course Name",
                    placeholder="It is recommended to keep the same names as in Lark Docs.",
                )
                lark_app_id = st.text_input(
                    "Lark App ID",
                    placeholder="Lark Docs URL: https://zhentouai.feishu.cn/base/{THIS STRING}?table=xxx...",
                )
                if st.form_submit_button(
                    "Add", type="primary", use_container_width=True
                ):
                    insert_course(user_name, course_name, lark_app_id)
                    st.rerun()
            pass

        add_vertical_space(2)

        "-----"
        "## Account Information"

        # Update User Information
        with st.expander("📝 Update User Information"):
            if st.session_state["authentication_status"]:
                try:
                    if authenticator.update_user_details(
                        username=st.session_state["username"],
                        fields={
                            "Form name": "Update User Information",
                            "Field": "Field to Update",
                            "Name": "User Name",
                            "Email": "Email",
                            "New value": "New Value",
                            "Update": "Update",
                        },
                    ):
                        with open("auth_config.yml", "w") as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success("User Information Updated Successfully")
                except Exception as e:
                    st.error(e)

        # add_vertical_space(1)

        # Reset Password
        with st.expander("🔑 Reset Password"):
            try:
                if authenticator.reset_password(
                    username=st.session_state["username"],
                    fields={
                        "Form name": "Reset Password",
                        "Current password": "Current Password",
                        "New password": "New Password",
                        "Repeat password": "Repeat New Password",
                        "Reset": "Reset",
                    },
                ):
                    with open("auth_config.yml", "w") as file:
                        yaml.dump(config, file, default_flow_style=False)
                    st.success("Password Reset Successfully")
            except Exception as e:
                st.error(e)

        add_vertical_space(1)

        "-----"
        # Logout
        if st.button("Logout", use_container_width=True):
            authenticator.logout(location="unrendered")
            st.session_state.is_login_welcome = False
