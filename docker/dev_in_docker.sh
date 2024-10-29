#!/bin/bash
script_path=$(dirname "$0")

docker build $script_path/../src/api -t ai-shifu-api-dev
docker build $script_path/../src/web -t ai-shifu-web-dev
docker build $script_path/../src/cook -t ai-shifu-cook-dev
docker compose -f $script_path/docker-compose-dev.yml up
