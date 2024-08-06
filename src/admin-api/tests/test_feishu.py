import random
import json


def test_feishu_create_app(app):
    # from flaskr.api.feishu import create_app
    # app_token = create_app(app, 'test_app')
    # print(app_token)

    '''
    {'code': 0, 'data': {'app': {'app_token': 'C1dEbAqp3aKDLOsFLDJct8W2n0e', 'default_table_id': 'tblldL3h9DcV2IO2', 'folder_token': '', 'name': 'test_app', 'time_zone': 'Asia/Shanghai', 'url': 'https://agiclass.feishu.cn/base/C1dEbAqp3aKDLOsFLDJct8W2n0e'}}, 'msg': 'success'}
.test app close
'''
    pass


def test_feishu_listfields(app):
    from flaskr.api.feishu import list_fields ,create_field
    fields = list_fields(app,'LLwmbSyMcakFVJsM5yacT5Gqnse','tblPI00k8B14kD5m')

    
    for field in fields.get('data',{}).get('items',[]):
        print('-'*20)
        print(field)
        field.pop('is_primary')
        field.pop('field_id')
        if field.get('description',None) != None:
            field.pop('description')
        if field.get('property',{}) != None:
            for option in field.get('property',{}).get('options',{}):
                option.pop('id')


        print("post field")
        print(field)
        r = create_field(app,'C1dEbAqp3aKDLOsFLDJct8W2n0e','tblldL3h9DcV2IO2',field)
        print(r)

    # print(fields)