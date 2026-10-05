# ============================================
# 调试：openai SDK 直接调用嵌入端点（复现 langchain 内部行为）
# 结果写入文件（避免终端编码干扰）
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent / "_probe_out.txt"
lines = []


def log(msg: str):
    lines.append(str(msg))
    OUT.write_text("\n".join(lines), encoding="utf-8")


from openai import OpenAI

from app.config import settings

client = OpenAI(
    api_key=settings.EMBED_API_KEY,
    base_url=settings.EMBED_BASE_URL,
)

log("== openai SDK 直接调用 ==")
try:
    resp = client.embeddings.create(
        model=settings.EMBED_MODEL_NAME,
        input=["西安旅游攻略", "成都火锅"],
    )
    log(f"✅ 成功，向量维度: {len(resp.data[0].embedding)}")
except Exception as e:
    log(f"❌ 失败: {type(e).__name__}: {e}")

log("\n== langchain OpenAIEmbeddings 调用（复现）==")
from langchain_openai import OpenAIEmbeddings

emb = OpenAIEmbeddings(
    model=settings.EMBED_MODEL_NAME,
    api_key=settings.EMBED_API_KEY,
    base_url=settings.EMBED_BASE_URL,
)
try:
    vecs = emb.embed_documents(["西安旅游攻略", "成都火锅"])
    log(f"✅ 成功，向量数: {len(vecs)}，维度: {len(vecs[0])}")
except Exception as e:
    log(f"❌ 失败: {type(e).__name__}: {e}")
    log("\n== 尝试修复1: 显式 encoding_format ==")
    try:
        resp = client.embeddings.create(
            model=settings.EMBED_MODEL_NAME,
            input=["西安旅游攻略"],
            encoding_format="float",
        )
        log(f"✅ encoding_format=float 成功，维度: {len(resp.data[0].embedding)}")
    except Exception as e2:
        log(f"❌ 失败: {e2}")
