from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis

# db = SQLAlchemy()
def init_db(app : Flask):
    global db
    app.logger.info('init db')
    if app.config.get('MYSQL_HOST',None) != None and app.config.get('MYSQL_PORT',None)!= None and app.config.get('MYSQL_DB',None) != None and app.config['MYSQL_USER'] != None and app.config.get('MYSQL_PASSWORD') != None:
        app.logger.info('init dbconfig from env')
        app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://'+app.config['MYSQL_USER']+':'+app.config['MYSQL_PASSWORD']+'@'+app.config['MYSQL_HOST']+':'+str(app.config['MYSQL_PORT'])+'/'+app.config['MYSQL_DB']
    else:
        app.logger.info('init dbconfig from config')
    db = SQLAlchemy()
    db.init_app(app)
    
def init_redis(app:Flask):
    global redis_client
    app.logger.info('init redis {} {} {}'
                    .format(app.config['REDIS_HOST'], app.config['REDIS_PORT'], app.config['REDIS_DB']))
    if app.config['REDIS_PASSWORD'] != '' and app.config['REDIS_PASSWORD'] != None:
        redis_client = Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], db=app.config['REDIS_DB'],password=app.config['REDIS_PASSWORD'],username=app.config.get('REDIS_USER',None))
    else:
        redis_client = Redis(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], db=app.config['REDIS_DB'])
    app.logger.info('init redis done')

def run_with_redis(ctx,key,timeout:int,func):
    with ctx:
        global redis_client
        lock = redis_client.lock(key, timeout=timeout, blocking_timeout=timeout)
        if lock.acquire(blocking=False):
            try:
                return func()
            finally:
                lock.release()
        else:
            return None
