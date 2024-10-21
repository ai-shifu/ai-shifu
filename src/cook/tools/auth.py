from contextlib import contextmanager

import streamlit as st
import streamlit_authenticator as stauth

import yaml
from yaml.loader import SafeLoader


def get_auth_and_config():
    with open("auth_config.yml") as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )
    return authenticator, config


@contextmanager
def login():
    authenticator, config = get_auth_and_config()
    authenticator.login()

    if st.session_state["authentication_status"]:
        yield authenticator, config
    else:
        status = st.session_state["authentication_status"]
        if status is False:
            st.error("Username/password is incorrect")
        elif status is None:
            st.warning("Please enter your username and password")
        st.stop()
