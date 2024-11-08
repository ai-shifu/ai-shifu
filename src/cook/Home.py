import streamlit as st
from streamlit_extras.add_vertical_space import add_vertical_space

st.set_page_config(
    page_title="Cook for AI-Shifu",
    page_icon="🧙‍♂️",
)

"""
# AI 师傅：课程制作中心
"""

add_vertical_space(3)
"""
## 首次使用
前往个人中心，使用初始密码登录后，修改密码。  (⬇️ 这是个真按钮，能点 ⬇️)
"""
if st.button("前往个人中心（My Account）", type="primary", use_container_width=True):
    st.switch_page("pages/100_My_Account.py")


add_vertical_space(3)
"""
## 管理课程
在个人中心（左侧菜单：【My Account】），可以管理课程，包括创建、修改、删除课程。

这里配置的课程将会出现在各个调试器页面中以供选择：
> ![](https://img.agiclass.cn/WX20240806-230115.png)
"""


add_vertical_space(3)
"""
## 章节剧本线性调试器
模拟用户端的体验，顺序的进行调试。  (⬇️ 这是个真按钮，能点 ⬇️)
"""
if st.button(
    "前往章节剧本线性调试器（Chapter Debugger）",
    type="primary",
    use_container_width=True,
):
    st.switch_page("pages/1_Chapter_Debugger.py")
"""
* 首次进入没有课程，需要前往个人中心配置课程：
> ![](https://img.agiclass.cn/WX20240806-232056.png)

* 有了课程之后就可以从想要的地方开始调试了：
> ![](https://img.agiclass.cn/WX20240806-232444.png)

* ⚠️ 注意: ⚠️  飞书中更新内容后要来清缓存：
> ![](https://img.agiclass.cn/WX20240806-232527.png)
>
> 加缓存是为了在飞书没有更新的时候，老师可以更快速的调整不同的位置进行调试
"""
