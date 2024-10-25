#!/bin/bash

if [ ! -f ".env" ]; then
    cp .env.example .env
fi



cd ../src/api
docker build ./ -t aishifu/ai-shifu-api:latest
cd ../web
docker build ./ -t aishifu/ai-shifu-web:latest
cd ../cook
docker build ./ -t aishifu/ai-shifu-cook:latest
cd ..
cd ..
cd docker
docker compose up
