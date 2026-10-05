# ============================================
# 调试：阿里云 MaaS 嵌入端点格式探测（只读测试，不改配置）
# 目标：确定该端点接受 OpenAI 兼容格式还是 dashscope 原生格式
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings

base = settings.EMBED_BASE_URL.rstrip("/")
key = settings.EMBED_API_KEY
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

print(f"端点: {base}")
print(f"模型: {settings.EMBED_MODEL_NAME}")

# 测试1：OpenAI 兼容格式
print("\n== 测试1: OpenAI 格式 POST /embeddings ==")
r1 = httpx.post(
    f"{base}/embeddings",
    headers=headers,
    json={"model": settings.EMBED_MODEL_NAME, "input": ["西安旅游攻略"]},
    timeout=30,
)
print(f"  状态: {r1.status_code}")
print(f"  返回: {r1.text[:300]}")

# 测试2：dashscope 原生格式（input.contents）
print("\n== 测试2: dashscope 原生格式 POST /embeddings ==")
r2 = httpx.post(
    f"{base}/embeddings",
    headers=headers,
    json={"model": settings.EMBED_MODEL_NAME, "input": {"contents": ["西安旅游攻略"]}},
    timeout=30,
)
print(f"  状态: {r2.status_code}")
print(f"  返回: {r2.text[:300]}")
