#!/bin/bash

# Initialize nvm
export NVM_DIR="/root/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# Define error handling function
handle_error() {
    echo "Error on line $1"
    exit 1
}

# Register error handling
trap 'handle_error $LINENO' ERR

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Load the specific Node.js version
nvm use v20.14.0

# Change to the project directory
cd /item/ai-shifu/src/admin-web/



# Check for untracked files and handle them
if [ -n "$(git status --porcelain)" ]; then
    echo "Untracked files detected. Cleaning up..."
    git clean -fd
fi

# Reset any changes and pull the latest code forcefully





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


# Ensure pnpm is installed using the npm full path
if ! command -v pnpm &> /dev/null; then
    echo "pnpm not found, installing..."
    npm install -g pnpm
fi

# Install dependencies with pnpm
pnpm install

# Build the project with pnpm
CI=false pnpm run build

# Sync build files to the specified directory
rsync -av --delete /item/ai-shifu/src/admin-web/build/ /opt/1panel/apps/openresty/openresty/www/sites/backend-test.pillowai.cn/index




sh $script_dir/send_feishu.sh "admin-web 部署成功" "部署成功！"

echo "Deployment completed successfully."
