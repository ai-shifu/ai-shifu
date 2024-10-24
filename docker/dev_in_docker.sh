#!/bin/bash

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

cd ../src/api
docker build ./ -t ai-shifu-api-dev
cd ../web
docker build ./ -t ai-shifu-web-dev
cd ../cook
docker build ./ -t ai-shifu-cook-dev
cd ..
cd ..
cd docker
docker compose -f ./docker-compose-dev.yml up
