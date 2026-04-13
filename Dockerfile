FROM node:22-alpine3.21 AS webui-builder

WORKDIR /webui

COPY webui/package.json webui/package-lock.json ./

RUN npm ci

COPY webui ./

RUN npm run build


FROM python:3.12-alpine3.21 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

RUN python -m venv /opt/venv

COPY README.md setup.py requirements*.txt ./
COPY hubvault ./hubvault
COPY tools ./tools
COPY --from=webui-builder /webui/dist ./webui/dist

RUN python tools/webui_sync.py --dist-dir ./webui/dist --target-dir ./hubvault/server/static/webui \
    && pip install --upgrade pip setuptools wheel \
    && pip install '.[full]'


FROM python:3.12-alpine3.21

ENV PATH="/opt/venv/bin:${PATH}" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HUBVAULT_HOST=0.0.0.0 \
    HUBVAULT_PORT=9472 \
    HUBVAULT_SERVE_MODE=frontend \
    HUBVAULT_REPO_PATH=/data/repo \
    HUBVAULT_INIT=1 \
    HUBVAULT_INITIAL_BRANCH=main

WORKDIR /app

RUN apk add --no-cache libstdc++

COPY --from=builder /opt/venv /opt/venv
COPY docker/entrypoint.sh /usr/local/bin/hubvault-entrypoint

RUN chmod +x /usr/local/bin/hubvault-entrypoint \
    && mkdir -p /data/repo

VOLUME ["/data/repo"]

EXPOSE 9472

ENTRYPOINT ["hubvault-entrypoint"]
