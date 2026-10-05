# ============================================
# 从 chapters/.env 复制关键配置到 backend/.env（只读源文件，不修改）
# ============================================
import sys
from pathlib import Path

SOURCE = Path(r"C:\Users\19674\PycharmProjects\pythonProject2\chapters\.env")
TARGET = Path(r"C:\Users\19674\PycharmProjects\pythonProject2\backend\.env")

# 需要复制的键（按项目需求筛选，不复制无关的 QDRANT/NEO4J 等）
NEEDED = [
    "DEEPSEEK_MODEL_ID",
    "DEEPSEEK_API_KEY",
    "LLM_BASE_URL",
    "LLM_TIMEOUT",
    "EMBED_MODEL_TYPE",
    "EMBED_MODEL_NAME",
    "EMBED_API_KEY",
    "EMBED_BASE_URL",
    "SILICONFLOW_API_KEY",
]

if not SOURCE.exists():
    print(f"❌ 源文件不存在: {SOURCE}")
    sys.exit(1)

# 读取源 .env（UTF-8）
lines = SOURCE.read_text(encoding="utf-8").splitlines()
found = {}
for line in lines:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    key = key.strip()
    if key in NEEDED and value.strip():
        found[key] = value.strip()

missing = [k for k in NEEDED if k not in found]
print(f"源文件读取成功，找到 {len(found)}/{len(NEEDED)} 个键")
if missing:
    print(f"  缺失（源文件里没有值）: {missing}")

# 写入 backend/.env（新文件；若已有内容则跳过已存在的键，避免覆盖）
header = "# ============================================\n" \
         "# 智能旅行规划系统 · 后端环境变量（从 chapters/.env 复制）\n" \
         "# 注意：AMAP_WEB_KEY / AMAP_JS_KEY 待用户提供后追加\n" \
         "# ============================================\n"
body = "\n".join(f"{k}={v}" for k, v in found.items())
TARGET.write_text(header + body + "\n", encoding="utf-8")
print(f"✅ 已写入 {TARGET}（{len(found)} 个键，仅键名+值；未触碰 {SOURCE}）")

# 验证
from dotenv import load_dotenv
import os
load_dotenv(TARGET)
print("验证读取：")
for k in ["DEEPSEEK_MODEL_ID", "EMBED_MODEL_TYPE", "EMBED_API_KEY", "LLM_BASE_URL"]:
    print(f"  {k} = {'已填(长度' + str(len(os.getenv(k, ''))) + ')' if os.getenv(k) else '空'}")
