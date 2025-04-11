import oss2

from tools.utils import st, time
from tools.auth import login
from init import cfg, load_dotenv, find_dotenv, os

_ = load_dotenv(find_dotenv())


# ==================== 各种初始化工作 ====================
# 设置页面标题和图标
st.set_page_config(
    page_title="Image Uploader | Cook for AI-Shifu",
    page_icon="🧙‍♂️",
)

# 页面内的大标题小标题
"# 图片上传 📤🖼️📤"
st.caption("")

# 需要登录
with login():

    # 初始化 OSS bucket 对象
    if "bucket" not in st.session_state:
        st.session_state.bucket = oss2.Bucket(
            oss2.Auth(
                cfg.OSS_ACCESS_KEY_ID,
                cfg.OSS_ACCESS_KEY_SECRET,
            ),
            cfg.IMG_OSS_ENDPOINT,
            cfg.IMG_OSS_BUCKET,
        )

    # ==================== 图片上传 ====================
    uploaded_files = st.file_uploader(
        "选择图片文件（png/jpg），支持一次上传多个图片",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    for uploaded_file in uploaded_files:
        # 获取文件名
        file_name = uploaded_file.name
        # st.write("filename:", uploaded_file.name)

        # 创建本地文件的存储路径
        file_path = os.path.join(cfg.IMG_LOCAL_DIR, file_name)

        bytes_data = uploaded_file.read()

        # 文件保存到本地
        with open(file_path, "wb") as f:
            # 直接将上传的文件内容写入到指定的文件
            f.write(uploaded_file.getvalue())

        # 文件上传到OSS
        st.session_state.bucket.put_object(file_name, bytes_data)

        st.success(
            f"文件 '{file_name}' 上传成功，URL如下（鼠标Hover后 右侧会出现复制按钮）："
        )
        st.code(f"https://{cfg.IMG_OSS_ANAME}/{file_name}")

    "---------------"
    # ==================== 图片管理 ====================
    "### 已上传图片列表："
    img_files = []
    # 加载 Bucket 下的所有文件
    for obj in oss2.ObjectIteratorV2(st.session_state.bucket):
        img_files.insert(
            0,
            {
                "缩略图": f"https://{cfg.IMG_OSS_ANAME}/{obj.key}?x-oss-process=image/resize,h_50,m_lfit",
                "文件名": obj.key,
                "大小": f"{obj.size / 1024 / 1024:.2f} MB",
                "最后修改时间": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(obj.last_modified)
                ),
                "URL": f"https://{cfg.IMG_OSS_ANAME}/{obj.key}",
            },
        )

    edited_df = st.data_editor(
        img_files,
        column_config={
            "缩略图": st.column_config.ImageColumn(),
            # '大小': st.column_config.Column(width='small'),
            # '最后修改时间': st.column_config.Column(width='small'),
            "URL": st.column_config.Column(width="small"),
        },
        use_container_width=True,
    )
