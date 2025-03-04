import requests

COURSE = {}
# COURSE["tblk9OFSKLeUPunv"]=["开篇","vewlGkI2Jp",401]#tblk9OFSKLeUPunv
# # COURSE["tbl41CFTMha7pU1d"]=["测试开篇","vewlGkI2Jp",401]#tblk9OFSKLeUPunv
# COURSE["tblPI00k8B14kD5m"]=["AI编程初体验","vewlGkI2Jp",402]
# # COURSE["tbl7G4WqBtv6hycy"]=["借助AI读懂代码","vewlGkI2Jp",402]
# # COURSE["tblFrdiqdXzebDZa"]=["判断代码的质量","vewlGkI2Jp",402]
# # COURSE["tbl93C7esgLzrtNT"]=["用AI做代码调试","vewlGkI2Jp",402]
# # COURSE["tbl9MytJGjsfvhvT"]=["用AI调整代码","vewlGkI2Jp",402]
# COURSE["tblDUfFbHGnM4LQl"]=["通义灵码","vewlGkI2Jp",405]
# COURSE["tbl9gl38im3rd1HB"]=["Copilot","vewlGkI2Jp",405]
# COURSE["tbl6bRlnHZ24ogP4"]=["Windows 上配置Python","vewlGkI2Jp",405]
# COURSE["tblQhi1ZutfUhW2T"]=["Mac上配置Python","vewlGkI2Jp",405]

HOST = "http://127.0.0.1:5800"
# HOST="https://test-api-sifu.agiclass.cn/"


# lesson_type 定义

# 401 课程

# LESSON_TYPE_TRIAL=401
# LESSON_TYPE_NORMAL=402
# LESSON_TYPE_EXTEND=403
# LESSON_TYPE_BRANCH=404
# LESSON_TYPE_BRANCH_HIDDEN=405
# LESSON_TYPES = {
#     "试用课":LESSON_TYPE_TRIAL,
#     "正式课":LESSON_TYPE_NORMAL,
#     "延展课":LESSON_TYPE_EXTEND,
#     "分支课":LESSON_TYPE_BRANCH,
#     "隐藏分支课":LESSON_TYPE_BRANCH_HIDDEN
# }


COURSE["tbldUsmPMh6vcBxh"] = ["开篇", "vewlGkI2Jp", 401]
COURSE["tblglFEDj2MqkLc3"] = ["如何用 AI 写出程序？", "vewlGkI2Jp", 402]
COURSE["tblJxFaqo31vAwYm"] = ["如何用 AI 来学习 python ？", "vewlGkI2Jp", 402]
COURSE["tblPI00k8B14kD5m"] = ["AI 编程运行的初体验", "vewlGkI2Jp", 402]
COURSE["tbl7G4WqBtv6hycy"] = ["如何借助 AI 读懂代码？", "vewlGkI2Jp", 402]
COURSE["tblFrdiqdXzebDZa"] = ["如何用 AI 优化代码质量？", "vewlGkI2Jp", 402]
COURSE["tbl93C7esgLzrtNT"] = ["如何用 AI 处理运行错误", "vewlGkI2Jp", 402]
COURSE["tbl9MytJGjsfvhvT"] = ["用 AI 完成一个简单的程序", "vewlGkI2Jp", 402]
COURSE["tbl9MytJGjsfvhvT"] = ["初学者怎么用 AI 自动补代码？", "vewlGkI2Jp", 402]
COURSE["tblDUfFbHGnM4LQl"] = ["通义灵码", "vewlGkI2Jp", 405]
COURSE["tbl9gl38im3rd1HB"] = ["Copilot", "vewlGkI2Jp", 405]
COURSE["tbl6bRlnHZ24ogP4"] = ["Windows 上配置Python", "vewlGkI2Jp", 405]
COURSE["tblQhi1ZutfUhW2T"] = ["Mac上配置Python", "vewlGkI2Jp", 405]
COURSE["tblQhi1ZutfUhW2T"] = ["Mac上配置Python3", "vewlGkI2Jp", 405]
COURSE["tblQhi1ZutfUhW2T"] = ["Mac上配置Python2", "vewlGkI2Jp", 405]

i = 0
for k in COURSE.keys():
    print(k)
    print(COURSE.get(k))
    name = COURSE.get(k)
    url = """{}/api/lesson/update_lesson?doc_id=IjfsbaLaQah0Wts1VaDcq0ePnGe&table_id={}&view_id={}&title={}&index={}&lesson_type={}""".format(
        HOST, k, name[1], name[0], i, name[2]
    )
    i = i + 1
    print(url)
    print(requests.get(url=url).json())
