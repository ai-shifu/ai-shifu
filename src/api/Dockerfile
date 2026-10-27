ARG SRC_ROOT=src
ARG API_SRC=${SRC_ROOT}/api
ARG I18N_SRC=${SRC_ROOT}/i18n

FROM python:3.11.17@sha256:a12cfee69f94b70fc1d4b25003cd96705f129f383cdeb32090f060ae04d00ec8 AS base

# Re-declare build args within this stage for COPY path expansion
ARG SRC_ROOT
ARG API_SRC
ARG I18N_SRC

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1

# Preserve the legacy mirror override; refresh trust on deb822-based images too.
RUN if [ -f /etc/apt/sources.list ]; then \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list; \
    sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    . /etc/os-release && \
    case "$VERSION_CODENAME" in \
      bookworm) minimum_ca='20250419~deb12u2' ;; \
      trixie) minimum_ca='20250419+deb13u1' ;; \
      *) echo "Unsupported Debian release: $VERSION_CODENAME"; exit 1 ;; \
    esac && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge "$minimum_ca" && \
    update-ca-certificates --fresh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ${API_SRC}/requirements.txt ./requirements.txt
# Bootstrap from hash-verified wheels before the first package-index request.
# pip vendors its own certifi bundle independently of the application's certifi.
RUN python -m pip install --no-deps --no-index --upgrade \
    'pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70' \
    'certifi @ https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl#sha256=42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b'
RUN python -m pip install --upgrade setuptools wheel
RUN python -m pip install -r requirements.txt && \
    test "$(python -c 'import certifi; print(certifi.__version__)')" = '2026.10.19' && \
    test "$(python -c 'import pip._vendor.certifi as certifi; print(certifi.__version__)')" = '2026.10.19'

COPY ${API_SRC} ./
COPY ${I18N_SRC} /app/i18n

FROM python:3.11.17-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

ENV SHARED_I18N_ROOT=/app/i18n

# Install FFmpeg for audio processing (pydub dependency)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    . /etc/os-release && \
    case "$VERSION_CODENAME" in \
      bookworm) minimum_ca='20250419~deb12u2' ;; \
      trixie) minimum_ca='20250419+deb13u1' ;; \
      *) echo "Unsupported Debian release: $VERSION_CODENAME"; exit 1 ;; \
    esac && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge "$minimum_ca" && \
    update-ca-certificates --fresh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# COPY merges directories, so remove the runner's old pip metadata and scripts first.
RUN python -m pip uninstall --yes pip

COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11 /usr/local/bin/
COPY --from=base /usr/local/bin/celery /usr/local/bin/celery
COPY --from=base /usr/local/bin/flask /usr/local/bin/flask
COPY --from=base /usr/local/bin/gunicorn /usr/local/bin/gunicorn

RUN test "$(python -c 'from importlib.metadata import distributions; print(",".join(d.version for d in distributions() if d.metadata["Name"].lower() == "pip"))')" = '26.2.2' && \
    test "$(python -c 'import pip; print(pip.__version__)')" = '26.2.2' && \
    test "$(python -m pip --version)" = "$(pip --version)" && \
    test "$(python -m pip --version)" = "$(pip3 --version)" && \
    test "$(python -m pip --version)" = "$(pip3.11 --version)"

WORKDIR /app

COPY --from=base /app /app

EXPOSE 5800

CMD gunicorn -k gthread --threads 8 -w 4 -b 0.0.0.0:5800 "app:app" --timeout 300 --log-level info --access-logfile /var/log/app.log --capture-output
