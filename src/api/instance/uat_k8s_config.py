
SQLALCHEMY_DATABASE_URI = 'mysql://userai:cloudtest.123A@cloude-test-mysql8-namj.cloud-test:3306/ai_asistant?charset=utf8mb4'

SQLALCHEMY_POOL_SIZE =20
SQLALCHEMY_POOL_TIMEOUT = 30
SQLALCHEMY_POOL_RECYCLE = 3600
SQLALCHEMY_MAX_OVERFLOW = 20

PLUGIN_CHAT_SYSTEM_MSG = "You are 小卡助理, always providing users with accurate and human-like responses, and helping them with scheduling tasks. You use save_memory and search to have a memory similar to humans. You serve users within China and your responses comply with relevant policies and regulations. Your functionality is based on Chinese lifestyle and culture."


SENDCLOUD_USER = "geyunfei_hit_test_4168kb"
SENDCLOUD_KEY = "8dc379ed9a133f1edb24cc343d8fda54"



CORS_LOGGING = True


REDIS_HOST = "cloud-test-redis-fym6.cloud-test"


REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = ""

JWT_KEY = "Pa88word"
TOKEN_EXPIRE_TIME = 3600*24*7

REDIS_KEY_PRRFIX = "ai:asistant:"
REDIS_KEY_PRRFIX_USER = REDIS_KEY_PRRFIX + "user:"
REDIS_KEY_PRRFIX_RESET_PWD = REDIS_KEY_PRRFIX + "reset_pwd:"
RESET_PWD_CODE_EXPIRE_TIME = 60*5


PATH_PREFIX=''

OPENAI_DEFAULT_MODEL = "gpt-3.5-turbo-0613"




MILVUS_HOST = "milvus-openai-test-proxy.openai-test"

MILVUS_PORT = 19530
MILVUS_USER = "root"


MILVUS_PASSWORD = "password"


MILVUS_ALIAS = "default"


LOGGING_PATH = "/var/log/ai-asistant.log"




LANGFUSE_PUBLIC_KEY='pk-lf-0c9190c8-6e11-4006-b7ef-ee9542b530d6'
LANGFUSE_SECRET_KEY='sk-lf-0e69cb12-d439-4045-9dc1-ef2f68011056'
# LANGFUSE_HOST='http://123.57.143.145:32002'
LANGFUSE_HOST='http://langfuse-server-node.langfuse-gpt:3000'