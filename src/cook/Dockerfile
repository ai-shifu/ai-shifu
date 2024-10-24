FROM python:3.11

# It is recommended to configure apt mirror sources within China.
# RUN if [ -f /etc/apt/sources.list ]; then \
#     sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list; \
#     sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
#     apt-get update && \
#     apt-get install -y python3-pip && \
#     apt-get clean && \
#     rm -rf /var/lib/apt/lists/*; \
#     else \
#     echo "No sources.list found!"; \
#     fi


WORKDIR /app
RUN pip install --upgrade pip

# It is recommended to configure pip mirror sources within China.
# ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
# ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the contents of the current directory to the /app directory in the container
COPY . .

# Declare that the service runs on port 8501
EXPOSE 8501


CMD ["streamlit", "run", "Home.py","--server.port=8501","--server.address=0.0.0.0"]

# EditorConfig is awesome: https://EditorConfig.org

# top-most EditorConfig file
root = true

# Unix-style newlines with a newline ending every file
[*]
end_of_line = lf
insert_final_newline = true

# Matches multiple files with brace expansion notation
# Set default charset
[*.{js,tsx}]
charset = utf-8
indent_style = space
indent_size = 2


# Matches the exact files either package.json or .travis.yml
[{package.json,.travis.yml}]
indent_style = space
indent_size = 2
