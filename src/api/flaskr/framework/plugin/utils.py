from flask import current_app


def unwrap_function(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    current_app.logger.info(f"unwrap_function {func.__name__}")
    return func
