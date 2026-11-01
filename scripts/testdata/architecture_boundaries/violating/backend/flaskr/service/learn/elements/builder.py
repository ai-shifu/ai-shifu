"""Exercise an element module that reaches up into the lesson host."""

from flaskr.service.learn.host.run import run_script


def build_elements() -> object:
    return run_script
