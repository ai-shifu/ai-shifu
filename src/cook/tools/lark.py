import logging
import os
import json
from enum import Enum

import streamlit as st
from dotenv import load_dotenv, find_dotenv
import lark_oapi as lark
from lark_oapi.api.auth.v3 import *
from lark_oapi.api.bitable.v1 import *


_ = load_dotenv(find_dotenv())
LARK_APP_ID = os.environ.get('LARK_APP_ID')
LARK_APP_SECRET = os.environ.get('LARK_APP_SECRET')


def get_lark_client() -> lark.Client:
    """ 获取 飞书 client 对象
    :return: client
    """
    client = (lark.Client.builder()
              .app_id(LARK_APP_ID)
              .app_secret(LARK_APP_SECRET)
              .log_level(lark.LogLevel.DEBUG)
              .build())
    return client


def get_tenant_access_token():
    client = get_lark_client()

    # 构造请求对象
    request = (InternalTenantAccessTokenRequest.builder()
               .request_body(InternalTenantAccessTokenRequestBody.builder()
                             .app_id(LARK_APP_ID)
                             .app_secret(LARK_APP_SECRET)
                             .build())
               .build())

    # 发起请求
    response: InternalTenantAccessTokenResponse = client.auth.v3.tenant_access_token.internal(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.auth.v3.tenant_access_token.internal failed, "
            f"code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.raw.content, indent=4))

    # 解析 token
    data = json.loads(response.raw.content)
    token = data.get('tenant_access_token', "Tenant access token not found")

    return token


@st.cache_data(show_spinner="Fetching bitables from Lark...")
def get_bitable_tables(app_token) -> Optional[list[AppTable]]:
    client = get_lark_client()

    # 构造请求对象
    request = (ListAppTableRequest.builder()
               .app_token(app_token)
               .build())

    # 发起请求
    response: ListAppTableResponse = client.bitable.v1.app_table.list(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table.list failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))

    return response.data.items


def get_bitable_records(app_token, table_id, view_id) -> Optional[list[AppTableRecord]]:
    client = get_lark_client()

    # 构造请求对象
    request = (SearchAppTableRecordRequest.builder()
               .app_token(app_token)
               .table_id(table_id)
               .page_size(500)
               .request_body(SearchAppTableRecordRequestBody.builder()
                             .view_id(view_id)
                             .build())
               .build())

    # 发起请求
    response: SearchAppTableRecordResponse = client.bitable.v1.app_table_record.search(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.search failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


    logging.info(f"是否有更多：{response.data.has_more}")
    logging.info(f"共有 {response.data.total} 条记录")

    return response.data.items


if __name__ == '__main__':
    # token = get_tenant_access_token()
    # print(token)

    # from init import cfg
    # items = get_bitable_records(cfg.LARK_APP_TOKEN, cfg.DEF_LARK_TABLE_ID, cfg.DEF_LARK_VIEW_ID)
    # print(items)

    items = get_bitable_tables('NlBbbzxRkaF986sUZTTcNdixnSi')
    print(items[0].table_id)
