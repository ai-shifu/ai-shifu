## 兼容性的配置文件
## 用于兼容不同的配置文件
### 1. 先从环境变量中读取
### 2. 如果环境变量中没有，则从配置文件中读取
### 3. 如果配置文件中也没有，则使用默认值

import os
from typing import Any 
from flask import Flask
from flask import Config as FlaskConfig

from flaskr.service.common.models import AppException


class Config(FlaskConfig):
    def __init__(self, parent: FlaskConfig,app:Flask, defaults: dict = {}):
        global __INSTANCE__
        self.parent = parent
        self.app = app
        __INSTANCE__ = self
    def __getitem__(self, key: Any) -> Any:
        if key in os.environ:
            return os.environ[key]
        return self.parent.__getitem__(key)
    def __getattr__(self, key: Any) -> Any:
        if key in os.environ:
            return os.environ[key]
        return self.parent.__getattr__(key)
    def __setitem__(self, key: Any, value: Any) -> None:
        self.app.logger.info("set {}={}".format(key,value))
        self.parent.__setitem__(key,value)
        os.environ[key] = str(value)
    def get(self, key: Any, default: Any = None) -> Any:
        self.app.logger.info("get {}".format(key))
        if key in os.environ:
            return os.environ[key]
        return self.parent.get(key,default)
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.parent.__call__(*args, **kwds)
    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key in os.environ:
            return os.environ[key]
        return self.parent.setdefault(key,default)
    


def get_config(key:str,default:Any=None)->Any:
    global __INSTANCE__
    if __INSTANCE__ is None:
        raise AppException("Config is not initialized")
    return __INSTANCE__.get(key,default)

