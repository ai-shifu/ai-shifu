from functools import wraps


# inject app to function and set inject flag
def inject(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        app = kwargs.get("app")
        if app:
            with app.app_context():
                return func(*args, **kwargs)
        return func(*args, **kwargs)

    wrapper.inject = True  # 设置标志属性
    return wrapper
