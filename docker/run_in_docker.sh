#!/bin/bash

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

cd docker
docker images | grep 'aishifu'  | awk -F ' ' '{print $3}' | xargs -I {} docker image rm {}
docker compose up
