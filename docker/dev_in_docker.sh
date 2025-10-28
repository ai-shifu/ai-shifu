#!/bin/bash
script_path=$(dirname "$0")

docker build -f $script_path/../src/api/Dockerfile -t ai-shifu-api-dev $script_path/..
docker build $script_path/../src/web -t ai-shifu-web-dev -f $script_path/../src/web/Dockerfile_DEV
docker build $script_path/../src/cook-web -t ai-shifu-cook-web-dev -f $script_path/../src/cook-web/Dockerfile_DEV
docker compose -f $script_path/docker-compose-dev.yml up
