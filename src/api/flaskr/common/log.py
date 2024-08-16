import logging
import os
from flask import Flask,g ,request
import uuid
from logging.handlers import TimedRotatingFileHandler
import threading
import socket
from datetime import datetime
import pytz
thread_local = threading.local() 
class RequestFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # 创建时区信息
        bj_time = pytz.timezone('Asia/Shanghai')
        # 转换 record.created（一个浮点数时间戳）到北京时间
        ct = datetime.fromtimestamp(record.created, bj_time)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            try:
                s = ct.isoformat(timespec='milliseconds')
            except TypeError:
                s = ct.isoformat()
        return s
    def format(self, record):
        try:
            record.url = getattr(thread_local, 'url', 'No_URL')
            record.request_id = getattr(thread_local, 'request_id', 'No_Request_ID')
            record.client_ip = getattr(thread_local, 'client_ip', 'No_Client_IP')
        except RuntimeError:
            record.url = "No_URL"
            record.request_id = "No_Request_ID"
            record.client_ip = "No_Client_IP"
        return super().format(record)

def init_log(app:Flask)->Flask:
    @app.before_request
    def setup_logging():
        thread_local.request_id = uuid.uuid4().hex
        thread_local.url = request.path
            # 尝试从 X-Forwarded-For 头部获取 IP 地址
        if 'X-Forwarded-For' in request.headers:
            user_ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
        else:
            # 如果没有 X-Forwarded-For 头部，就使用 remote_addr
            user_ip = request.remote_addr
        request.client_ip = user_ip
        thread_local.client_ip = user_ip

    host_name = socket.gethostname()
    
    log_format = '%(asctime)s [%(levelname)s] ai-shifu.com/ai-sifu '+host_name+' %(client_ip)s %(url)s %(request_id)s %(message)s'
    formatter = RequestFormatter(log_format)
    
    log_file = app.config.get('LOGGING_PATH', 'logs/ai-sifu.log')
    # 如果目录不存在，创建目录
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # 按天切割日志 
    file_handler = TimedRotatingFileHandler(app.config['LOGGING_PATH'], when='midnight', backupCount=7)
    file_handler.setFormatter(formatter)
    # 控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    if 'gunicorn' in os.getenv('SERVER_SOFTWARE', ''):
        gunicorn_logger = logging.getLogger('gunicorn.info')
        if gunicorn_logger.handlers:
            for handler in gunicorn_logger.handlers:
                handler.setFormatter(formatter)
            app.logger.handlers = gunicorn_logger.handlers.copy()  # 使用gunicorn的处理器
        else:
            app.logger.handlers = []
            app.logger.addHandler(file_handler)  # 仅在没有gunicorn处理器时添加
        app.logger.addHandler(console_handler)  # 控制台处理器始终添加
        app.logger.setLevel(gunicorn_logger.level)
    else:
        app.logger.handlers = []  # 清空默认处理器
        app.logger.addHandler(file_handler)  # 如果是主程序，则添加
        app.logger.addHandler(console_handler)  # 控制台处理器始终添加
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False  # 停止向上传播
    app.logger.setLevel(logging.INFO)
    app.logger.error('Logging setup complete')
    return app 