"""Reject product and framework imports from the independent engine."""

import flask
from flaskr.service.learn.agent.models import LearnAgentSession
from flaskr.service.profile.api import SYS_USER_NICKNAME
from sqlalchemy.orm import Session


def application_dependencies() -> tuple:
    return flask, LearnAgentSession, SYS_USER_NICKNAME, Session
