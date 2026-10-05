# ============================================
# 后端镜像：FastAPI + Chroma + SQLite
# 构建：docker compose build backend
# 说明：
#   - data/ 由 compose 挂载到 /app/data 持久化（SQLite 行程库 + Chroma 向量库）
#   - .env 由 compose 的 env_file 注入进程环境，不打进镜像（见 .dockerignore）
# ============================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖：requirements 不变时可复用这层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码与随镜像分发的数据（攻略 md / 检索规则 / 评估集）
# 注意：chroma_db 与 *.db 已在 .dockerignore 排除，避免把本机数据打进镜像
COPY app ./app
COPY data ./data
COPY eval ./eval
COPY scripts ./scripts

EXPOSE 8000

# 容器内无需热重载
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
