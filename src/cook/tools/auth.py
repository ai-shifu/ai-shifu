import logging

import streamlit as st
import streamlit_authenticator as stauth

import yaml
from yaml.loader import SafeLoader


def get_authenticator():
    with open('auth_config.yml') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        config['pre-authorized']
    )
    return authenticator, config


def login():
    # st.write(st.session_state)
    # if 'username' not in st.session_state:
    logging.debug('=== need login')
    authenticator, config = get_authenticator()

    # 初始化登录成功欢迎记录
    if 'is_login_welcome' not in st.session_state:
        st.session_state.is_login_welcome = False

    login_result = authenticator.login()

    if login_result[1]:
        if not st.session_state.is_login_welcome:
            st.toast(f'欢迎回来，{st.session_state["name"]}', icon='🎈')
            st.session_state.is_login_welcome = True
        return authenticator, config
    else:
        return False, False
    # else:
    #     logging.debug(f'username: {st.session_state.username}')
    #     return True, True



