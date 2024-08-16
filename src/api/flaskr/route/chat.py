from flask import Flask, request, Response,g
from .. import api
import uuid
from flaskr.service.chat import get_chat_list, get_chat

from .common import make_common_response


def register_chat_route(app: Flask, path_prefix: str):
    @app.route(path_prefix+'/chat-assistant', methods=['POST'])
    def chat_assistant():
        user_id = request.user.user_id
        user_input = request.get_json().get('msg', '')
        chat_id = request.get_json().get('chat_id', '')
        return Response(api.ChatFunSSE(app,user_input, chat_id, user_id), mimetype="text/event-stream")

    @app.route(path_prefix+'/chat-list', methods=['GET'])
    def chat_list():
        user_id = request.user.user_id
        chat_title = request.args.get('chat_title', '')
        return make_common_response(get_chat_list(app, user_id, chat_title))

    @app.route(path_prefix+'/chat-detail', methods=['GET'])
    def chat_detail():
        user_id = request.user.user_id
        chat_id = request.args.get('chat_id')
        return make_common_response(get_chat(app, user_id, chat_id))


    return app
