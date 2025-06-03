from flaskr.service.shifu.utils import get_original_outline_tree
from .test_utils import dump


def test_get_original_outline_tree(app):
    with app.app_context():
        data = get_original_outline_tree(app, "282851210b7d4ecbb46e8a39b938fd78")
        dump(data)
