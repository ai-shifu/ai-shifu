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

#  switch to project dir
cd src/api || exit

# get git commit hash
GIT_COMMIT=$(git rev-parse --short HEAD)


RANDOM_STRING=$(openssl rand -hex 2)




IMAGE_TAG="v1-$GIT_COMMIT-$RANDOM_STRING"
IMAGE_NAME="sifu-api"
DOCKERFILE_PATH="Dockerfile"

REGISTRY="registry.cn-beijing.aliyuncs.com/agix"





latest_commit=$(git log -1 --pretty=format:"%H")
author=$(git log -1 --pretty=format:"%an")
date=$(git log -1 --pretty=format:"%ad")
message=$(git log -1 --pretty=format:"%s")

#  merge commi
is_merge_commit=$(git log -1 --merges --pretty=format:"%H")

if [ "$latest_commit" == "$is_merge_commit" ]; then
    # get merged commits
    merged_commits=$(git show --pretty=format:"%P" -s $latest_commit | xargs -n1 git log --pretty=format:"哈希: %H, 作者: %an, 提交信息: %s" -n 1)

    git_msg="最近的提交是一个合并提交：\n提交哈希: $latest_commit\n作者: $author\n提交时间: $date\n合并信息: $message\n被合并的提交有：\n$merged_commits"
else
    git_msg="最近的提交信息：\n提交哈希: $latest_commit\n作者: $author\n提交时间: $date\n提交信息: $message"
fi


echo $git_msg

echo "Building Docker image..."
docker build -t "$IMAGE_NAME:$IMAGE_TAG" -f "$DOCKERFILE_PATH" .

echo "Tagging Docker image..."
docker tag "$IMAGE_NAME:$IMAGE_TAG" "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

echo "Pushing Docker image to registry..."
docker push "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

TARGET_PORT=5800
FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

CONTAINER_ID=$(docker ps -q -f "publish=$TARGET_PORT")

if [ -n "$CONTAINER_ID" ]; then
    EXISTING_CONTAINER_NAME=$(docker inspect --format '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    echo "Stopping existing container $EXISTING_CONTAINER_NAME..."
    docker stop "$EXISTING_CONTAINER_NAME"

    echo "Removing existing container $EXISTING_CONTAINER_NAME..."
    docker rm "$EXISTING_CONTAINER_NAME"
else
    echo "No running container found on port $TARGET_PORT."
fi

ADMIN_TARGET_PORT=5801

FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

CONTAINER_ID=$(docker ps -q -f "publish=$ADMIN_TARGET_PORT")

if [ -n "$CONTAINER_ID" ]; then
    EXISTING_CONTAINER_NAME=$(docker inspect --format '{{.Name}}' "$CONTAINER_ID" | sed 's/^\/\(.*\)/\1/')

    echo "Stopping existing container $EXISTING_CONTAINER_NAME..."
    docker stop "$EXISTING_CONTAINER_NAME"

    echo "Removing existing container $EXISTING_CONTAINER_NAME..."
    docker rm "$EXISTING_CONTAINER_NAME"
else
    echo "No running container found on port $TARGET_PORT."
fi
CONTAINER_NAME="sifu_api_v1_$TIMESTAMP"
echo "Starting a new container with the name $CONTAINER_NAME..."
docker run --env-file  /item/.env  -v /data/cert/pingxx_test_key.gem:/key/pingxx_test_key.gem -v /data/logs/api:/var/log/ -p $TARGET_PORT:5800 --name "$CONTAINER_NAME" -d "$FULL_IMAGE_NAME"
docker run --env-file  /item/.admin.env  -v /data/cert/pingxx_test_key.gem:/key/pingxx_test_key.gem -v /data/logs/api:/var/log/ -p $ADMIN_TARGET_PORT:5800 --name "ADMIN$CONTAINER_NAME" -d "$FULL_IMAGE_NAME"

sh $script_dir/send_feishu.sh "sifu_api_v1 部署成功" "$CONTAINER_NAME $FULL_IMAGE_NAME 部署成功！\n $git_msg "

echo "Deployment completed successfully."
