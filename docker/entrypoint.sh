#!/bin/sh
set -eu

: "${HUBVAULT_HOST:=0.0.0.0}"
: "${HUBVAULT_PORT:=9472}"
: "${HUBVAULT_SERVE_MODE:=frontend}"
: "${HUBVAULT_REPO_PATH:=/data/repo}"
: "${HUBVAULT_INIT:=1}"
: "${HUBVAULT_INITIAL_BRANCH:=main}"

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

if [ -z "${HUBVAULT_TOKEN_RO:-}" ] && [ -z "${HUBVAULT_TOKEN_RW:-}" ]; then
    echo "HUBVAULT_TOKEN_RW or HUBVAULT_TOKEN_RO must be set." >&2
    echo "Example: docker run -e HUBVAULT_TOKEN_RW=dev-token ..." >&2
    exit 2
fi

mkdir -p "${HUBVAULT_REPO_PATH}"

exec python -c "from hubvault.server import launch; launch()"
