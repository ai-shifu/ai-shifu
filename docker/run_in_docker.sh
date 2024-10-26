#!/bin/bash

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

cd docker
docker compose up
