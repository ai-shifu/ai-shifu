from node:20-slim
# 使用官方的node运行时作为父镜像
RUN corepack enable
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"


# 设置工作目录
WORKDIR /usr/src/app

# 安装项目依赖
# 复制package.json和package-lock.json文件
COPY package*.json ./

# 复制ecosystem.config.js文件
COPY ecosystem.config.js ./

# 复制项目源代码
COPY . .

RUN pnpm install




# 构建项目
RUN pnpm run build

RUN pnpm install -g serve

RUN pnpm install -g pm2



# 声明服务运行在5000端口
EXPOSE 5000


ENV REACT_APP_BASEURL='http://localhost:5800/'

# 启动服务
CMD ["pm2-runtime", "ecosystem.config.js"]
