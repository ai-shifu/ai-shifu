
from langfuse import Langfuse
from flask import Flask 

def init_langfuse(app: Flask):
    global langfuse_client 
    langfuse_client= Langfuse(
    public_key= app.config["LANGFUSE_PUBLIC_KEY"],
    secret_key= app.config["LANGFUSE_SECRET_KEY"],
    host= app.config["LANGFUSE_HOST"]
    )
