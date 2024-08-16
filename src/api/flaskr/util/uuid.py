from flask import Flask
import uuid
# 生产一个uuid
def generate_id(app:Flask)->str:
    return  str(uuid.uuid4()).replace('-', '')