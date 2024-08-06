import requests
from flask import Flask 
import pytest
# from .common import create_app


  


# from ..dao import redis_client

def test_get_access_token(app):
    from flaskr.api.llm.ernie import get_access_token
    access_token = get_access_token()
    app.logger.info(access_token)
    assert get_access_token() != ''
    

def test_chat(app):
    from flaskr.api.llm.ernie import get_ernie_response
    get_ernie_response(app,"ERNIE-Speed-8K","你好")