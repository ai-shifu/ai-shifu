import json
import os
import time
import logging
from flask import Flask, Response, g,request,send_from_directory,make_response
from flask_cors import CORS


import pymysql
pymysql.install_as_MySQLdb()
from flasgger import Swagger



def create_app(test_config=None):

    # 在程序开始时调用 patch_pyppeteer()
    app = Flask(__name__, instance_relative_config=True)
    CORS(app, resources={r"/*": {"supports_credentials": True}})
    app.logger.info('config: {}'.format(test_config))
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )
    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.logger.info('test_config is not None, load the '+test_config+'_config.py')
        app.config.from_pyfile(test_config+'_config.py', silent=True)

    ##  加载配置文件å
    from .common import Config,init_log
    app.config = Config(app.config)
    ## 初始化日志
    init_log(app)
    ## 初始化数据库
    from . import dao



    
    dao.init_db(app)
    dao.init_redis(app)

    ## 初始化其他API
    from . import api
    api.init_langfuse(app)
  
    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    

    # 初始化rute 
    from . import route
    prefix = app.config.get('PATH_PREFIX','')
    app = route.register_common_handler(app)
    app = route.register_user_handler(app,prefix+'/user')
    app = route.register_lesson_handler(app,prefix+'/lesson')
    app = route.register_study_handler(app,prefix+'/study')
    app = route.register_dict_handler(app,prefix+'/dict')
    app = route.register_tools_handler(app,prefix+'/tools')
    app = route.register_order_handler(app,prefix+'/order')
    app = route.register_admin_handler(app,prefix+'/admin')

    ## 初始化swagger

    if app.config.get('SWAGGER_ENABLED',False):
        from .common import swagger_config
        app.logger.info('swagger init ...')
        swagger = Swagger(app,config=swagger_config,merge=True)

    return app