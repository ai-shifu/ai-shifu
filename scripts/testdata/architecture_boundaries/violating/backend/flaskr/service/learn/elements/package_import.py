"""Exercise host and follow-up modules imported as children of their packages."""

from flaskr.service.learn.ask import context
from flaskr.service.learn.host import run


def load_host_modules() -> tuple[object, object]:
    return context, run
