
from flask import Flask 
import requests
import json
from datetime import datetime
import pytz
import urllib.parse
from flaskr.common.config import get_config

# 飞书相关的调用封装
# ref: https://open.feishu.cn/document/server-docs/docs/docs-overview

# APPID = 'cli_a5fbaacf14fb900c'
# APP_SECRET='VnReMkkkPdUf6e6kCvkgPgvJJybQvvxe'
# FOLDER_ID='QSN2fIQWqlubNxdHHoJcSbVknVh'
# REDIS_KEY_PREFIX = 'feishu:token:'



## AI 课程
APPID = get_config("FEISHU_APP_ID") 
#'cli_a69aa732b7381013'
APP_SECRET= get_config("FEISHU_APP_SECRET")
FOLDER_ID='QSN2fIQWqlubNxdHHoJcSbVknVh'
REDIS_KEY_PREFIX = 'feishu:token:'



# 设置东八区时区
TIME_ZONE = pytz.timezone('Asia/Shanghai')


def get_tenat_token(app:Flask):
    from ..dao import redis_client as redis
    token = redis.get(REDIS_KEY_PREFIX+'token')
    if token:
        app.logger.info('get_tenat_token:'+str(token,encoding="utf-8"))
        return str(token,encoding="utf-8")
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/'
    headers = {'Content-Type': 'application/json'}
    data = {
        "app_id": APPID,
        "app_secret": APP_SECRET
    }
    r = requests.post(url, headers=headers, data=json.dumps(data))
    app.logger.info('get_tenat_token:'+str(r.status_code))
    app.logger.info('get_tenat_token:'+str(r.text))
    app.logger.info('get_tenat_token:'+str(r.json()))
    expire = r.json()['expire']
    redis.set(REDIS_KEY_PREFIX+'token',str(r.json()['tenant_access_token']),expire)
    return r.json()['tenant_access_token']



def create_document(app:Flask,title:str):

    token = get_tenat_token(app)
    url = 'https://open.feishu.cn/open-apis/docx/v1/documents'
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    data = {

        "folder_token": FOLDER_ID,
        "title": title,
        
    }
    r = requests.post(url, headers=headers, data=json.dumps(data))
    app.logger.info('create_document:'+str(r.json()))
    doc_id =  r.json()['data']['document']['document_id']
    
    return doc_id
def update_document_to_public(app:Flask,doc_id:str):
    token = get_tenat_token(app)
    url = 'https://open.feishu.cn/open-apis/drive/v2/permissions/{doc_id}/public?type=docx'.format(doc_id=doc_id)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    app.logger.info('update doc to public:'+url)
    data = {
        "link_share_entity":"anyone_readable",
        "external_access_entity":"open",
    }

    r = requests.patch(url,headers=headers,data=json.dumps(data))
    app.logger.info('update_docment_to_public:'+str(r.json()))
    return r.json()
  


def add_text_element(app:Flask,doc_id:str,user_name:str,text:str):
    token = get_tenat_token(app)
    url = 'https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children'.format(doc_id=doc_id)
    app.logger.info('add_text_element:'+url)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    data = {
        "children": [
            {
                "block_type": 13,
                "ordered": {
                    "elements": [
                        {
                            "text_run": {
                                "content":datetime.now(TIME_ZONE).strftime("%H:%M")+" "+ user_name+":  ",
                                "text_element_style":{
                                    "bold":True
                                }
                            }
                        },
                         {
                            "text_run": {
                                "content":text,
                                
                            }
                        }
                    ],
                }
                
            }
        ]
    }
    r = requests.post(url, headers=headers, data=json.dumps(data))
    app.logger.info('add_text_element:'+str(r.json()))
    return r.json()
def remove_text_element(app:Flask,doc_id:str,block_id:str):
    token = get_tenat_token(app)

    url = 'https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}'.format(document_id=doc_id,block_id=doc_id)
    app.logger.info('get_txt_element:'+url)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    r = requests.get(url, headers=headers)
    app.logger.info('get_txt_element:'+str(r.json()))
    blocks = r.json()['data']['block']['children']

    index = blocks.index(block_id)
    url = 'https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{block_id}/children/batch_delete'.format(doc_id=doc_id,block_id=doc_id)
    app.logger.info('remove_text_element:'+url)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    r = requests.delete(url, headers=headers, data=json.dumps({
    "start_index": index,
    "end_index": index+1
        }))
    app.logger.info('remove_text_element:'+str(r.json()))
    return r.json()




## 以下是表格相关的操作
## ref: https://open.feishu.cn/document/ukTMukTMukTM/uEDO04SM4QjLxgDN
## 逻辑
## 1. 列出所有的表格
## 2. 列出表格的所有视图
## 3. 获取表格的所有数据

## 一篇多维表格可以理解成是一个 app，他的唯一标识就是 app_token。
## app 是由一个个 table 组成，我们称 table 为数据表，他的标识就是 table_id。
## table 由 record(记录) 和 field(字段) 组成, 同时可以拥有多个 view (视图)。






def get_document_info(app:Flask,doc_id:str,block_id:str):
    token = get_tenat_token(app)
    url = 'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables'.format(app_token=doc_id)
    app.logger.info('get_txt_element:'+url)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    r = requests.get(url, headers=headers)
    app.logger.info('get_txt_element:'+str(r.json()))
    return r.json()


def list_views(app:Flask,app_token:str,table_id:str):
    token = get_tenat_token(app)
    # https://open.feishu.cn/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views
    url = 'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views'.format(app_token=app_token,table_id=table_id)
    app.logger.info('list_views:'+url)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    r = requests.get(url, headers=headers)
    app.logger.info('list_views:'+str(r.json()))
    return r.json()





def list_records(app:Flask,app_token:str,table_id:str,view_id:str=None,page_token:str=None,page_size:int=None):
    token = get_tenat_token(app)
    # https://open.feishu.cn/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search
    url = 'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search'.format(app_token=app_token,table_id=table_id)
    query={}
    if page_token:
        query['page_token']=page_token
    if page_size:
        query['page_size']=page_size
    

    app.logger.info('list_records:'+url)
    url  = f"{url}?{urllib.parse.urlencode(query)}" if query else url
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    body = {
     
        "automatic_fields": True,
    }
    if view_id:
        body["view_id"]= view_id
    app.logger.info('list_records:'+str(body))
    r = requests.post(url, headers=headers,data=json.dumps(body))
    # app.logger.info('list_records:'+str(r.json()))
    
    return r.json() 


''' 列出数据表
'''
def list_tables(app:Flask,app_token:str):
    token = get_tenat_token(app)
    url = "https://open.feishu.cn/open-apis/bitable/v1/apps/{token}/tables".format(app_token=app_token)
    headers = {'Content-Type': 'application/json','Authorization':'Bearer '+token}
    r = requests.get(url,headers=headers)
    return r.json()
   

