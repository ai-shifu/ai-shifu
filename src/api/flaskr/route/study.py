from flask import Flask, Response,request 
from flaskr.route.common import  make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.lesson.funs import AICourseDTO
from flaskr.service.study import  get_lesson_tree_to_study, get_study_record, run_script 


def register_study_handler(app:Flask,path_prefix:str)->Flask:

    @app.route(path_prefix+'/run',methods=['POST'])
    def run_lesson_script():
        '''
        运行课程脚本
        ---
        tags:
        - 学习
        parameters:
            -   in: body
                name: body
                description: 运行课程脚本的请求体
                required: true
                schema:
                    type: object
                    properties:
                        course_id:
                            type: string
                            default: dfca19aab2654fe4882e002a58567240
                            description: 课程id
                        lesson_id:
                            type: string
                            description: 课时id
                        input:
                            type: string
                            description: 输入内容
                        input_type:
                            type: string 
                            default: start
                            description: 输入类型（默认为 start）
                        script_id:  
                            type: string
                            description: 脚本ID,如果为空则运行下一条，否则运行指定脚本
        responses:
            200:
                description: 返回脚本运行结果
                
                content:
                    text/event-stream:
                        schema:
                             $ref: "#/components/schemas/ScriptDTO"
        '''
        course_id = request.get_json().get('course_id', 'dfca19aab2654fe4882e002a58567240')
        lesson_id = request.get_json().get('lesson_id', None)
        script_id = request.get_json().get('script_id', None)
        input = request.get_json().get('input', None)
        input_type = request.get_json().get('input_type','start')
        if course_id =="" or course_id is None:
            course_id = 'dfca19aab2654fe4882e002a58567240' 
        user_id = request.user.user_id
        return Response(run_script(app,course_id=course_id,lesson_id=lesson_id,user_id=user_id,input=input,input_type=input_type,script_id = script_id), mimetype="text/event-stream")
   

    @app.route(path_prefix+'/get_lesson_tree', methods=['GET'])
    

    def get_lesson_tree_study():
        """
        获取课程树
        ---
        tags:
        - 学习
        parameters:
        -   name: course_id
            in: query
            type: string
            required: true
            description: 课程ID
        responses:
            200:
                description: 返回课程树
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/AICourseDTO"
            400:
                description: 参数错误
        """
        course_id = request.args.get('course_id')
        if not course_id:
            raise_param_error("doc_id is not found")
        user_id =request.user.user_id 
        return make_common_response(get_lesson_tree_to_study(app,user_id,course_id))
    @app.route(path_prefix+'/get_lesson_study_record', methods=['GET'])
    def get_lesson_study_record():
        """
        获取课程学习记录
        ---
        tags:
        - 学习
        parameters:
        -   name: lesson_id
            in: query
            type: string
            required: true
            description: 课时ID
        responses:
            200:
                description: 返回课程学习记录
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: 返回码
                                message:
                                    type: string
                                    description: 返回信息
                                data:
                                    $ref: "#/components/schemas/StudyRecordDTO"
            400:
                description: 参数错误
        """
        lesson_id = request.args.get('lesson_id')
        if not lesson_id:
            raise_param_error("lesson_id is not found")
        user_id =request.user.user_id
        return make_common_response(get_study_record(app,user_id,lesson_id))
 
    


    return app