#!/bin/bash

# 获取 Git 提交哈希的简短版本
GIT_COMMIT=$(git rev-parse --short HEAD)
TIMESTAMP=$(date "+%m%d%H%M")
# 使用 openssl 生成一个额外唯一的随机字符串
RANDOM_STRING=$(openssl rand -hex 2)
# 组合组件生成镜像标签
IMAGE_TAG="v1-$GIT_COMMIT-$RANDOM_STRING"
LATETST_TAG="latest"
IMAGE_NAME="ai-shifu-api"
DOCKERFILE_PATH="Dockerfile"


echo "Building Docker image..."
echo "IMAGE_TAG:$IMAGE_TAG"
echo "IMAGE_NAME:$IMAGE_NAME"
echo "DOCKERFILE_PATH:$DOCKERFILE_PATH"



# 设置 Docker 镜像仓库信息
REGISTRY="registry.cn-beijing.aliyuncs.com/agix"

# 构建 Docker 镜像
echo "Building Docker image..."
docker buildx build --platform linux/amd64 -t "$IMAGE_NAME:$IMAGE_TAG" -f "$DOCKERFILE_PATH" .

# 给 Docker 镜像打标签
echo "Tagging Docker image..."
echo "IMAGE: $REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REGISTRY/$IMAGE_NAME:$LATETST_TAG"

# 推送 Docker 镜像到仓库
echo "Pushing Docker image to registry..."
docker push "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
echo "Pushing Docker latest image to registry..."
docker push "$REGISTRY/$IMAGE_NAME:$LATETST_TAG"
