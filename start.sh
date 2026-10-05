#!/usr/bin/env bash
# ============================================
# 智能旅行规划系统 · 本地启动脚本（Linux / macOS）
# 用法：bash start.sh
# 功能：1) 确保 Redis 在跑  2) 校验高德 Key  3) 启动后端 uvicorn
#      前端单独：cd frontend && npm run dev
# 对应 Windows 版：start.ps1
# ============================================
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"

# ---- 1. Redis ----
if command -v redis-cli >/dev/null 2>&1 && redis-cli -p 6379 ping >/dev/null 2>&1; then
  echo "[1/3] Redis 已在运行 (端口 6379)"
elif command -v redis-server >/dev/null 2>&1; then
  echo "[1/3] 启动 Redis ..."
  redis-server --port 6379 --daemonize yes >/dev/null 2>&1 || true
  sleep 1
else
  echo "[1/3] 未找到 Redis。可用 Docker 起：docker compose up -d redis"
  echo "      后端会『优雅降级』继续工作，只是天气/POI 每次都要重查，较慢。"
fi

# ---- 2. 校验高德 Key ----
if [ -f "$BACKEND/.env" ]; then
  if grep -qE '^AMAP_WEB_KEY=.+' "$BACKEND/.env"; then
    echo "[2/3] 高德 Web Key 已配置"
  else
    echo "[2/3] 高德 Web Key 未配置：注册 https://lbs.amap.com/ 后填入 backend/.env"
  fi
else
  echo "[2/3] backend/.env 不存在：请复制 backend/.env.example 并填写"
fi

# ---- 3. 启动后端 ----
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
    echo "[3/3] 未找到 .venv，改用系统 python3（建议先建 .venv 并安装 backend/requirements.txt）"
  else
    echo "[3/3] 找不到 Python：请创建虚拟环境并安装 backend/requirements.txt" >&2
    exit 1
  fi
else
  echo "[3/3] 启动后端 http://127.0.0.1:8000 ..."
fi

cd "$BACKEND"
exec "$PY" -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
