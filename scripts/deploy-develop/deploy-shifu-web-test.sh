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
cd /item/ai-shifu/src/web/

# Check for untracked files and handle them
if [ -n "$(git status --porcelain)" ]; then
    echo "Untracked files detected. Cleaning up..."
    git clean -fd
fi

# Reset any changes and pull the latest code forcefully
git fetch --all
git reset --hard origin/develop

# Ensure pnpm is installed using the npm full path
if ! command -v pnpm &> /dev/null; then
    echo "pnpm not found, installing..."
    npm install -g pnpm
fi

# Install dependencies with pnpm
pnpm install

# Build the project with pnpm
pnpm run build

# Sync build files to the specified directory
rsync -av --delete /item/ai-shifu/src/web/build/ /opt/1panel/apps/openresty/openresty/www/sites/test-sifu.agiclass.cn/index

sh $script_dir/send_feishu.sh "sifu_web 部署成功" "部署成功！"

echo "Deployment completed successfully."
