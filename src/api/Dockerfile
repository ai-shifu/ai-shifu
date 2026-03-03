ARG SRC_ROOT=src
ARG API_SRC=${SRC_ROOT}/api
ARG I18N_SRC=${SRC_ROOT}/i18n

FROM python:3.11 AS base

# Re-declare build args within this stage for COPY path expansion
ARG SRC_ROOT
ARG API_SRC
ARG I18N_SRC

WORKDIR /app

COPY ${API_SRC}/requirements.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

COPY ${API_SRC} ./
COPY ${I18N_SRC} /app/i18n

FROM python:3.11-slim

ENV SHARED_I18N_ROOT=/app/i18n

# Install FFmpeg for audio processing (pydub dependency).
# Use a stable mirror and retry apt operations to reduce transient CI failures.
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' /etc/apt/sources.list; \
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
        sed -i 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
    fi; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/99-ci-retries; \
    update_success=0; \
    for attempt in 1 2 3; do \
        if apt-get update; then \
            update_success=1; \
            break; \
        fi; \
        echo "apt-get update failed (attempt ${attempt}), retrying..."; \
        sleep $((attempt * 5)); \
    done; \
    if [ "${update_success}" -ne 1 ]; then \
        echo "apt-get update failed after retries"; \
        exit 1; \
    fi; \
    apt-get install -y --no-install-recommends ffmpeg; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin/flask /usr/local/bin/flask
COPY --from=base /usr/local/bin/gunicorn /usr/local/bin/gunicorn

WORKDIR /app

COPY --from=base /app /app

EXPOSE 5800

CMD gunicorn -k gevent -w 4 -b 0.0.0.0:5800 "app:app" --timeout 300 --log-level info --access-logfile /var/log/app.log --capture-output
