"""Exercise a cross-service import violation."""

from flaskr.route.user import register_user_handler
from flaskr.service.learn.funcs import get_lesson_preview
from flaskr.service.learn.routes import register_learn_handler


def load_helpers() -> object:
    return register_user_handler, get_lesson_preview, register_learn_handler
