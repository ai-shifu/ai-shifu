"""Inject plugin dependencies into application components."""

from collections.abc import Callable
from functools import wraps


# inject app to function and set inject flag
def inject(func: object) -> Callable[..., object]:
    """Inject a plugin callback at the requested extension point."""

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        app = kwargs.get("app")
        if app:
            with app.app_context():
                return func(*args, **kwargs)
        return func(*args, **kwargs)

    wrapper.inject = True  # 设置标志属性
    return wrapper
