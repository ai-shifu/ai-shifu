"""Exercise host and follow-up modules imported as children of the learn package."""

from flaskr.service.learn import follow_up_context, runscript_v2


def load_host_modules() -> tuple[object, object]:
    return follow_up_context, runscript_v2
