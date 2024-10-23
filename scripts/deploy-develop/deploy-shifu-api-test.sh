#!/bin/bash

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 错误处理函数
handle_error() {
    echo "Error on line $1"
    exit 1
}

# 注册错误处理函数，当脚本遇到错误时执行 handle_error
trap 'handle_error $LINENO' ERR

# 生成唯一的时间戳
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# 切换到项目目录
cd /item/ai-shifu/src/api || exit

# 获取 Git 提交哈希的简短版本
GIT_COMMIT=$(git rev-parse --short HEAD)

# 使用 openssl 生成一个额外唯一的随机字符串
RANDOM_STRING=$(openssl rand -hex 2)



# 切换到 api 目录
cd /item/ai-shifu/src/api || exit

# 组合组件生成镜像标签
IMAGE_TAG="v1-$GIT_COMMIT-$RANDOM_STRING"
IMAGE_NAME="sifu-api"
DOCKERFILE_PATH="Dockerfile"

# 设置 Docker 镜像仓库信息
REGISTRY="registry.cn-beijing.aliyuncs.com/agix"





# 获取最近一次提交的基本信息
latest_commit=$(git log -1 --pretty=format:"%H")
author=$(git log -1 --pretty=format:"%an")
date=$(git log -1 --pretty=format:"%ad")
message=$(git log -1 --pretty=format:"%s")

# 检查是否为 merge 提交
is_merge_commit=$(git log -1 --merges --pretty=format:"%H")

if [ "$latest_commit" == "$is_merge_commit" ]; then
    # 获取被合并的提交
    merged_commits=$(git show --pretty=format:"%P" -s $latest_commit | xargs -n1 git log --pretty=format:"哈希: %H, 作者: %an, 提交信息: %s" -n 1)

    git_msg="最近的提交是一个合并提交：\n提交哈希: $latest_commit\n作者: $author\n提交时间: $date\n合并信息: $message\n被合并的提交有：\n$merged_commits"
else
    git_msg="最近的提交信息：\n提交哈希: $latest_commit\n作者: $author\n提交时间: $date\n提交信息: $message"
fi


echo $git_msg

# 构建 Docker 镜像
echo "Building Docker image..."
docker build -t "$IMAGE_NAME:$IMAGE_TAG" -f "$DOCKERFILE_PATH" .

# 给 Docker 镜像打标签
echo "Tagging Docker image..."
docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# 推送 Docker 镜像到仓库
echo "Pushing Docker image to registry..."
docker push "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# 部署 Docker 容器
# 固定变量
TARGET_PORT=5800

# 生成完整的镜像名称
FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# 查找使用目标端口的容器 ID
CONTAINER_ID=$(docker ps -q -f "publish=$TARGET_PORT")

if [ -n "$CONTAINER_ID" ]; then
    # 获取容器 ID 对应的容器名称
    EXISTING_CONTAINER_NAME=$(docker inspect --format '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    # 停止现有容器
    echo "Stopping existing container $EXISTING_CONTAINER_NAME..."
    docker stop "$EXISTING_CONTAINER_NAME"

    # 移除现有容器
    echo "Removing existing container $EXISTING_CONTAINER_NAME..."
    docker rm "$EXISTING_CONTAINER_NAME"
else
    echo "No running container found on port $TARGET_PORT."
fi

# 部署 Docker 容器
# 固定变量
ADMIN_TARGET_PORT=5801

# 生成完整的镜像名称
FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# 查找使用目标端口的容器 ID
CONTAINER_ID=$(docker ps -q -f "publish=$ADMIN_TARGET_PORT")

if [ -n "$CONTAINER_ID" ]; then
    # 获取容器 ID 对应的容器名称
    EXISTING_CONTAINER_NAME=$(docker inspect --format '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    # 停止现有容器
    echo "Stopping existing container $EXISTING_CONTAINER_NAME..."
    docker stop "$EXISTING_CONTAINER_NAME"

    # 移除现有容器
    echo "Removing existing container $EXISTING_CONTAINER_NAME..."
    docker rm "$EXISTING_CONTAINER_NAME"
else
    echo "No running container found on port $TARGET_PORT."
fi
# 使用更新的镜像和自定义容器名称运行新容器
CONTAINER_NAME="sifu_api_v1_$TIMESTAMP"
echo "Starting a new container with the name $CONTAINER_NAME..."
docker run --env-file  /item/.env  -v /data/cert/pingxx_test_key.gem:/key/pingxx_test_key.gem -v /data/logs/api:/var/log/ -p $TARGET_PORT:5800 --name "$CONTAINER_NAME" -d "$FULL_IMAGE_NAME"
docker run --env-file  /item/.admin.env  -v /data/cert/pingxx_test_key.gem:/key/pingxx_test_key.gem -v /data/logs/api:/var/log/ -p $ADMIN_TARGET_PORT:5800 --name "ADMIN$CONTAINER_NAME" -d "$FULL_IMAGE_NAME"

sh $script_dir/send_feishu.sh "sifu_api_v1 部署成功" "$CONTAINER_NAME $FULL_IMAGE_NAME 部署成功！\n $git_msg "
# 打印容器日志
echo "Container logs for $CONTAINER_NAME:"
docker logs "$CONTAINER_NAME"

echo "Deployment completed successfully."
