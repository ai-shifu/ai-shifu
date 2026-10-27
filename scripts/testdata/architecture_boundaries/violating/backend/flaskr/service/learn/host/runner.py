"""Exercise a host module that reaches up into the learn routes."""

from flaskr.service.learn.routes import register_learn_handler


def run_request() -> object:
    return register_learn_handler
