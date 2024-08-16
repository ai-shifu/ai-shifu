
from flask import Flask,g 
import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from flaskext.markdown import Markdown
import asyncio
from pyppeteer import launch
from ..service.smarthome import *
from ..service.schedule import * 
from ..service.contact import add_contact,get_contact
from ..service.document import create_new_document,append_to_document
from ..service.todo import create_new_todo,get_todos_by_user
from ..api.sendcloud import send_email


def get_company_cost(app:Flask,user_id,month):
    # 生成一年的mock数据 
    app.logger.info("查询公司月度运营费用:{}".format(month))
   # Generate a range of months from May 2022 to June 2023.
    start_date = datetime.datetime(2022, 5, 1)
    end_date = datetime.datetime(2023, 7, 31)

    months = [start_date]
    while months[-1] < end_date:
        months.append(months[-1] + timedelta(days=30)) # we add 30 days to get approximately next month

    # Generate the operation cost data for each month.
    data = {}
    for date in months:
        month_str = date.strftime("%Y-%m")
        data[month_str] = {
            "salaries": random.randint(10000, 20000),
            "maintenance": random.randint(1000, 2000),
            "rent": random.randint(2000, 4000),
            "advertisement": random.randint(1000, 2000),
            "electricity": random.randint(500, 1000),
            "water": random.randint(100, 300)
        }

    # Get the cost details for a specific month.
    cost_details = data.get(month)
    if cost_details is None:
        return "No data available for the specified month."
    msg =  "水费:{},电费:{},物业费:{},工资:{},总费用:{}".format(cost_details["water"],cost_details["electricity"],cost_details["maintenance"],cost_details["salaries"],cost_details["water"]+cost_details["electricity"]+cost_details["maintenance"]+cost_details["salaries"]) 
    app.logger.info(msg)
    return msg
