from flaskr.route.user import register_user_handler
from flaskr.service.learn.funcs import get_lesson_preview
from flaskr.service.learn.routes import register_learn_handler


def load_helpers():
    return register_user_handler, get_lesson_preview, register_learn_handler
