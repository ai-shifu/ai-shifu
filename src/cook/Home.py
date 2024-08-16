from PIL import Image
import streamlit as st

st.set_page_config(
    page_title="Assistants Demo",
    page_icon="🧬",
)

"""
# 香蕉🍌公司 AI 助手
> 请在左侧选择您需要的助理

这网站首页就是你向领导吹牛逼的地方，把这页当成是一页纸BP，把你的产品卖给领导。

**不要主动讲任何技术细节**

## 这是个啥
项目概述，简明的介绍核心功能
形式上丰富，内容上简要

![demo](app/static/pic.jpg)

"""

image = Image.open('static/didi.png')
st.image('static/didi.png')