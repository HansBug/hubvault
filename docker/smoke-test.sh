#!/usr/bin/env bash
set -euo pipefail

image_ref="${1:?image reference is required}"
port="${2:-9480}"
container_name="hubvault-smoke-${port}"
volume_name="hubvault-smoke-data-${port}"
payload_file="$(mktemp)"
frontend_file="$(mktemp)"
asset_file="$(mktemp)"

cleanup() {
    docker rm -f "${container_name}" >/dev/null 2>&1 || true
    docker volume rm -f "${volume_name}" >/dev/null 2>&1 || true
    rm -f "${payload_file}"
    rm -f "${frontend_file}"
    rm -f "${asset_file}"
}

wait_for_url() {
    local url="$1"
    local output_file="$2"
    for _ in $(seq 1 30); do
        if curl -fsS -H "Authorization: Bearer ci-token" "${url}" > "${output_file}" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done

    docker logs "${container_name}" || true
    return 1
}

trap cleanup EXIT

docker volume create "${volume_name}" >/dev/null

docker run -d \
    --name "${container_name}" \
    -e HUBVAULT_TOKEN_RW=ci-token \
    -e HUBVAULT_PORT="${port}" \
    -v "${volume_name}:/data/repo" \
    -p "${port}:${port}" \
    "${image_ref}" >/dev/null

wait_for_url "http://127.0.0.1:${port}/api/v1/meta/service" "${payload_file}"

docker run --rm \
    -v "${volume_name}:/data/repo" \
    "${image_ref}" \
    sh -c 'test -f /data/repo/FORMAT && test -f /data/repo/metadata.sqlite3'

docker rm -f "${container_name}" >/dev/null 2>&1 || true

docker run -d \
    --name "${container_name}" \
    -e HUBVAULT_TOKEN_RW=ci-token \
    -e HUBVAULT_INIT=0 \
    -e HUBVAULT_PORT="${port}" \
    -v "${volume_name}:/data/repo" \
    -p "${port}:${port}" \
    "${image_ref}" >/dev/null

wait_for_url "http://127.0.0.1:${port}/api/v1/meta/service" "${payload_file}"

wait_for_url "http://127.0.0.1:${port}/" "${frontend_file}"

grep -q '<title>hubvault</title>' "${frontend_file}"
asset_path="$(grep -oE '/assets/[^"]+' "${frontend_file}" | head -n 1)"
test -n "${asset_path}"
wait_for_url "http://127.0.0.1:${port}${asset_path}" "${asset_file}"

python3 - <<'PY' "${payload_file}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["service"] == "hubvault"
assert payload["mode"] == "frontend"
assert payload["repo"]["default_branch"] == "main"
assert payload["auth"]["can_write"] is True
PY
