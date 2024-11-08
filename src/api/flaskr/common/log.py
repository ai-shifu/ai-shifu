import logging
import os
from flask import Flask, request
import uuid
from logging.handlers import TimedRotatingFileHandler
import threading
import socket
from datetime import datetime
import pytz
import colorlog

thread_local = threading.local()


class RequestFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # create time zone info
        bj_time = pytz.timezone("Asia/Shanghai")
        # convert record.created (a float timestamp) to beijing time
        ct = datetime.fromtimestamp(record.created, bj_time)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            try:
                s = ct.isoformat(timespec="milliseconds")
            except TypeError:
                s = ct.isoformat()
        return s

    def format(self, record):
        try:
            request_id = getattr(thread_local, "request_id", "No_Request_ID")
            if request_id == "No_Request_ID":
                thread_local.request_id = uuid.uuid4().hex
                request_id = thread_local.request_id
            record.url = getattr(thread_local, "url", "No_URL")
            record.request_id = request_id
            record.client_ip = getattr(thread_local, "client_ip", "No_Client_IP")
        except RuntimeError:
            record.url = "No_URL"
            record.request_id = "No_Request_ID"
            record.client_ip = "No_Client_IP"
        return super().format(record)


def init_log(app: Flask) -> Flask:
    @app.before_request
    def setup_logging():

        # request_id = getattr(thread_local, "X-Request-ID", uuid.uuid4().hex)
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        mode = request.headers.get("X-API-MODE", "api")
        thread_local.mode = mode
        thread_local.request_id = request_id
        thread_local.url = request.path
        # try to get user ip from X-Forwarded-For header
        if "X-Forwarded-For" in request.headers:
            user_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            # if no X-Forwarded-For header, use remote_addr
            user_ip = request.remote_addr
        request.client_ip = user_ip
        thread_local.client_ip = user_ip

    host_name = socket.gethostname()

    log_format = (
        "%(asctime)s [%(levelname)s] ai-shifu.com/ai-sifu "
        + host_name
        + " %(client_ip)s %(url)s %(request_id)s %(funcName)s %(process)d %(message)s"
    )
    formatter = RequestFormatter(log_format)

    # color log format
    color_log_format = (
        "%(log_color)s%(asctime)s [%(levelname)s] ai-shifu.com/ai-sifu "
        + host_name
        + " %(client_ip)s %(url)s %(request_id)s %(funcName)s %(process)d %(message)s"
    )
    color_formatter = colorlog.ColoredFormatter(
        color_log_format,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    log_file = app.config.get("LOGGING_PATH", "logs/ai-sifu.log")
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = TimedRotatingFileHandler(
        app.config["LOGGING_PATH"], when="midnight", backupCount=7
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_formatter)  # use color formatter

    if "gunicorn" in os.getenv("SERVER_SOFTWARE", ""):
        gunicorn_logger = logging.getLogger("gunicorn.info")
        if gunicorn_logger.handlers:
            for handler in gunicorn_logger.handlers:
                handler.setFormatter(formatter)
            app.logger.handlers = gunicorn_logger.handlers.copy()
        else:
            app.logger.handlers = []
            app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        app.logger.setLevel(gunicorn_logger.level)
    else:
        app.logger.handlers = []
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False
    app.logger.setLevel(logging.INFO)
    app.logger.error("Logging setup complete")
    return app


def get_mode():
    return getattr(thread_local, "mode", None)
