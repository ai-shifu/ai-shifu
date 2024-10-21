cd ../src/api
docker build ./ -t ai-shifu-api-dev
cd ../web
docker build ./ -t ai-shifu-web-dev
cd ../admin-web
docker build ./ -t ai-shifu-admin-web-dev
cd ..
cd ..
cd docker
docker compose -f ./docker-compose-dev.yml up
