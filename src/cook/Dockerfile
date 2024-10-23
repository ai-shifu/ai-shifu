### 使用一个官方Python运行时作为父镜像
FROM python:3.9

# 确保 /etc/apt/sources.list 存在并更改APT源为国内的镜像源
RUN if [ -f /etc/apt/sources.list ]; then \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list; \
    sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
    apt-get update && \
    apt-get install -y python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*; \
    else \
    echo "No sources.list found!"; \
    fi

# 设置工作目录
WORKDIR /app

# # 设置pip镜像源
# ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
# ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt


# 复制当前目录内容到容器的/app内
COPY . .

# 声明服务运行在5800端口
EXPOSE 8501

# 启动streamlit服务
CMD streamlit run Home.py
