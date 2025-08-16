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
import requests

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


class FeishuLogHandler(logging.Handler):
    def __init__(self, webhook_url):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url

    def emit(self, record):
        log_entry = self.format(record)
        payload = {
            "msg_type": "text",
            "content": {"text": f"师傅出错啦！\n{log_entry}\n"},
        }
        try:
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            from flask import current_app

            current_app.logger.error(f"Failed to send log to Feishu: {e}")


class ColoredRequestFormatter(RequestFormatter, colorlog.ColoredFormatter):
    def __init__(self, fmt, **kwargs):
        super().__init__(fmt, **kwargs)


def init_log(app: Flask) -> Flask:
    @app.before_request
    def setup_logging():
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        thread_local.request_id = request_id
        thread_local.url = request.path
        if "X-Forwarded-For" in request.headers:
            user_ip = request.headers["X-Forwarded-For"].split(",")[0].strip()
        else:
            user_ip = request.remote_addr
        request.client_ip = user_ip
        thread_local.client_ip = user_ip
        if request.method == "POST":
            try:
                request_body = {}
                if request.files:
                    request_body["File Upload"] = "File Upload"
                elif request.is_json:
                    request_body["JSON"] = request.get_json(silent=True)
                elif request.form:
                    request_body["Form"] = request.form.to_dict()
                elif request.args:
                    request_body["Args"] = request.args.to_dict()
                elif request.form:
                    request_body["Form"] = request.form.to_dict()
                else:
                    request_body["Raw"] = request.get_data(as_text=True)
                app.logger.info(f"Request body: {request_body}")
            except Exception as e:
                app.logger.error(f"Failed to get request body: {e}")
        else:
            app.logger.info(f"Request method: {request.method}")

    @app.after_request
    def after_request(response):
        try:
            if response.headers.get(
                "Content-Type"
            ) and "text/event-stream" in response.headers.get("Content-Type"):
                app.logger.info("Response: <SSE streaming response>")

                @response.call_on_close
                def log_sse_end():
                    app.logger.info("SSE Response: <streaming ended>")

                return response
            if response.direct_passthrough:
                app.logger.info("Response: <streaming response omitted>")
                return response
            response_data = response.get_data(as_text=True)
            app.logger.info(f"Response: {response_data}")
        except Exception as e:
            app.logger.error(f"Error logging response: {str(e)}")
        return response

    host_name = socket.gethostname()
    log_format = (
        "%(asctime)s [%(levelname)s] ai-shifu.com/ai-shifu "
        + host_name
        + " %(client_ip)s %(url)s %(request_id)s %(funcName)s %(process)d %(message)s"
    )
    formatter = RequestFormatter(log_format)
    # color log format
    color_log_format = (
        "%(log_color)s%(asctime)s [%(levelname)s] ai-shifu.com/ai-shifu "
        + host_name
        + " %(client_ip)s %(url)s %(request_id)s %(funcName)s %(process)d %(message)s"
    )
    color_formatter = ColoredRequestFormatter(
        color_log_format,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    log_file = app.config.get("LOGGING_PATH", "logs/ai-shifu.log")
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = TimedRotatingFileHandler(log_file, when="midnight", backupCount=7)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_formatter)  # use color formatter

    from .config import get_config

    if "gunicorn" in get_config("SERVER_SOFTWARE"):
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
    feishu_webhook_url = app.config.get("FEISHU_LOG_WEBHOOK_URL", None)
    if feishu_webhook_url:
        app.logger.info("Feishu enabled.")
        feishu_handler = FeishuLogHandler(feishu_webhook_url)
        feishu_handler.setFormatter(formatter)
        app.logger.addHandler(feishu_handler)
    else:
        app.logger.info("Feishu disabled.")
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False
    return app
