# INSTALL FROM SOURCE CODE STEP BY STEP
## Prerequisites
### Concept
Firstly, look at the source code structure:
```
$ ls
api cook web
```
AI Shifu is composed of backend in `api` and frontend in `web`. And `cook` is the editor for the course.
So, we can

### Tools
- Python 3.11
- MySQL
- Redis
- Lark for script editing
- OSS for image storage

- OpenAI API Key or LLM Provider API Key

## Operating Steps

### Step 1: Clone the repository

```bash
git clone https://github.com/ai-shifu/ai-shifu.git
```


### Step 2: Configure environment variables

[More Info](https://github.com/ai-shifu/ai-shifu-docs/blob/main/zh_CN/guides/environment-variables.md)
```bash
cp docker/.env.example .env  # guess this is under the root folder
```

### Step 3: Configure .env
```
... skip code ...
########
# LLMs #
########

# IMPORTANT: At least one LLM should be enabled

# OpenAI
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_API_KEY="sk-proj-..."

... skip code ...

# Default LLM model. Supported models:
# OpenAI's models:
#   gpt-4o-latest, gpt-4o-mini, gpt-4, gpt-3.5-turbo, chatgpt-4o-latest, and their dated releases
... skip code ...

DEFAULT_LLM_MODEL="gpt-4o"

# Default LLM temperature
DEFAULT_LLM_TEMPERATURE=0.3

... skip code ...

# MySQL settings. If you don't know what they are, don't modify them.
SQLALCHEMY_DATABASE_URI="mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu"


# Redis settings. If you don't know what they are, don't modify them.
REDIS_HOST="ai-shifu-redis"
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=""
REDIS_USER=""



# (Optional) Alibaba Cloud settings for sending SMS and uploading files
ALIBABA_CLOUD_SMS_ACCESS_KEY_ID=""
ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET=""
ALIBABA_CLOUD_SMS_SIGN_NAME=""
ALIBABA_CLOUD_SMS_TEMPLATE_CODE=""

# Universal verification code
UNIVERSAL_VERIFICATION_CODE="1024"

# (Optional) Alibaba Cloud OSS settings for uploading files
ALIBABA_CLOUD_OSS_ACCESS_KEY_ID=""
ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET=""
ALIBABA_CLOUD_OSS_ENDPOINT="oss-cn-beijing.aliyuncs.com"
ALIBABA_CLOUD_OSS_BUCKET=""
ALIBABA_CLOUD_OSS_BASE_URL=""

ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID=""
ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET=""
ALIBABA_CLOUD_OSS_COURSES_ENDPOINT="oss-cn-beijing.aliyuncs.com"
ALIBABA_CLOUD_OSS_COURSES_BUCKET=""
ALIBABA_CLOUD_OSS_COURSES_URL=""

# (Optional) Langfuse settings for tracking LLM
LANGFUSE_PUBLIC_KEY=""
LANGFUSE_SECRET_KEY=""
LANGFUSE_HOST=""

# (Optional) NetEase YIDUN settings for content detection
NETEASE_YIDUN_SECRET_ID=""
NETEASE_YIDUN_SECRET_KEY=""
NETEASE_YIDUN_BUSINESS_ID=""

# Lark (Feishu) for script editing
LARK_APP_ID=""
LARK_APP_SECRET=""

... skip code ...

# Path of log file
LOGGING_PATH="/var/log/ai-shifu.log"  # make sure you have the permission to write to the file

# Website access domain name
WEB_URL=""

############
# Frontend #
############

# Service
REACT_APP_BASEURL="http://localhost:5800" # example as for local development
PORT=5000

# Eruda console
REACT_APP_ERUDA="true"







```

### Step 4: Run the application
* Make sure .env is under every folder

#### Step 4.1: Run the api
```bash
cd api
cp ../.env .env

pip install -r requirements.txt
flask db upgrade
gunicorn -w 4 -b 0.0.0.0:5800 'app:app' --timeout 300 --log-level debug --access-logfile /var/log/app.log --capture-output
```

#### Step 4.2: Run the web
```bash
cd web
cp ../.env .env

npm install  # or use pnpm install
npm run start:dev # or use pnpm run build
```

#### Step 4.3: Run the cook
1. Copy .env
```bash
cd cook
cp ../.env .env
```

2. Install requirements
```bash
pip install -r requirements.txt
```

3. Edit auth_config.yml
```bash
cp auth_config.example.yml auth_config.yml
```
4. Init database
```bash
# pay attention to the database name should be the same as the one in .env
mysql -u user -h xxxx -p database_name < ../../docker/init.sql
```

5. Run the cook
```bash
streamlit  run Home.py
```

## Step 5: Access the application
Go to the browser and have fun!
