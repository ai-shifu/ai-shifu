ARG SRC_ROOT=src
ARG API_SRC=${SRC_ROOT}/api
ARG I18N_SRC=${SRC_ROOT}/i18n

FROM python:3.11 AS base

# ensure /etc/apt/sources.list exists and change APT source to aliyun mirror
RUN if [ -f /etc/apt/sources.list ]; then \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list; \
    sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
    apt-get update && \
    apt-get install -y python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*; \
    else \
    echo "No sources.list found!"; \
    fi

WORKDIR /app

COPY ${API_SRC}/requirements.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

COPY ${API_SRC} ./
COPY ${I18N_SRC} /app/i18n

FROM python:3.11-slim

ENV SHARED_I18N_ROOT=/app/i18n

COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin/flask /usr/local/bin/flask
COPY --from=base /usr/local/bin/gunicorn /usr/local/bin/gunicorn

WORKDIR /app

COPY --from=base /app /app

EXPOSE 5800

CMD gunicorn -k gevent -w 4 -b 0.0.0.0:5800 "app:app" --timeout 300 --log-level info --access-logfile /var/log/app.log --capture-output
