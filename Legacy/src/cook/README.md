# codesifu-demo

## cook example .env
```
#################
# Editor (Cook) #
#################

# Database settings. If you don't know what they are, don't modify them.
COOK_DB_USERNAME="root"
COOK_DB_PASSWORD="ai-shifu"
COOK_DB_DATABASE="ai-shifu-cook"
COOK_DB_HOST="ai-shifu-mysql"

# For uploading images
COOK_IMG_LOCAL_DIR="/data/img/"
COOK_IMG_OSS_ANAME=""
COOK_IMG_OSS_ENDPOINT=""
COOK_IMG_OSS_BUCKET=""

# API environment
COOK_USE_API_ENV="prod"
# WEB URL is used to display the address of the course page and also serves as the prefix for the API URL (with "/api" added after it).
WEB_URL_TEST="http://ai-shifu-api:5800"
WEB_URL_PROD="http://ai-shifu-api:5800"

# Logs
COOK_LOG_LEVEL="DEBUG"
COOK_LOG_OUT_LEVEL="DEBUG"
COOK_LOG_DIR="/var/log/"
COOK_LOG_OUT_PATH="/var/log/ai-shifu-cook.log"
COOK_LOG_ERR_LEVEL="ERROR"
COOK_LOG_ERR_PATH="/var/log/ai-shifu-cook.err.log"

```
