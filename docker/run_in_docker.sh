#!/bin/bash

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

cd ../src/api
docker build ./ -t ai-shifu-api
cd ../web
docker build ./ -t ai-shifu-web
cd ..
cd ..
cd docker
docker compose up
