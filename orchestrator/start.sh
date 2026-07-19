#!/usr/bin/env bash

set -Eeuo pipefail

ORCHESTRATOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ORCHESTRATOR_DIR}/.." && pwd)"
FRONTEND_DIR="${ORCHESTRATOR_DIR}/frontend"
PUBLIC_PORT=8100
BACKEND_PORT=18100
BACKEND_PID=""
FRONTEND_PID=""

fail() {
  printf '启动失败：%s\n' "$1" >&2
  exit 1
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${BACKEND_PID}${FRONTEND_PID}" ]]; then
    printf '\n正在关闭 Orchestrator 前后端...\n'
  fi

  for pid in "${BACKEND_PID}" "${FRONTEND_PID}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done

  for pid in "${BACKEND_PID}" "${FRONTEND_PID}"; do
    if [[ -n "${pid}" ]]; then
      wait "${pid}" 2>/dev/null || true
    fi
  done

  exit "${exit_code}"
}

command -v conda >/dev/null 2>&1 || fail "未找到 conda。"
command -v node >/dev/null 2>&1 || fail "未找到 Node.js。"

ACCOUNT_PREFIX="$(
  conda run -n account python -c 'import sys; print(sys.prefix)'
)" || fail "无法使用 Conda account 环境。"
ACCOUNT_PYTHON="${ACCOUNT_PREFIX}/bin/python"

[[ -x "${ACCOUNT_PYTHON}" ]] || fail "account 环境中没有可执行的 Python。"
"${ACCOUNT_PYTHON}" -c 'import dynaconf, fastapi, mcp, openai_codex, pydantic, uvicorn' \
  >/dev/null 2>&1 \
  || fail "account 环境缺少依赖，请先安装 orchestrator/requirements.txt 和 orchestrator/backend/requirements.txt。"

[[ -x "${ORCHESTRATOR_DIR}/node_modules/.bin/codex" ]] \
  || fail "Codex runtime 未安装，请运行 npm ci --prefix orchestrator。"
[[ -x "${FRONTEND_DIR}/node_modules/.bin/vite" ]] \
  || fail "编排器前端依赖未安装，请运行 npm ci --prefix orchestrator/frontend。"

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "${REPO_ROOT}"

printf '正在启动 Orchestrator：http://127.0.0.1:%s\n' "${PUBLIC_PORT}"
"${ACCOUNT_PYTHON}" -m uvicorn orchestrator.backend.main:app \
  --host 127.0.0.1 \
  --port "${BACKEND_PORT}" &
BACKEND_PID=$!

(
  cd "${FRONTEND_DIR}"
  ORCHESTRATOR_BACKEND_PORT="${BACKEND_PORT}" \
    exec ./node_modules/.bin/vite \
      --port "${PUBLIC_PORT}" \
      --strictPort
) &
FRONTEND_PID=$!

printf '前后端已启动。按 Ctrl+C 可同时关闭。\n'

while true; do
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    set +e
    wait "${BACKEND_PID}"
    service_status=$?
    set -e
    printf 'Orchestrator 后端已退出（状态码 %s）。\n' "${service_status}" >&2
    exit "${service_status}"
  fi

  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    set +e
    wait "${FRONTEND_PID}"
    service_status=$?
    set -e
    printf 'Orchestrator 前端已退出（状态码 %s）。\n' "${service_status}" >&2
    exit "${service_status}"
  fi

  sleep 1
done
