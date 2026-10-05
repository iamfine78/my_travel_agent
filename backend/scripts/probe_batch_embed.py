# ============================================
# 调试：批量嵌入 400 的具体原因
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent / "_probe_out.txt"
lines = []


def log(msg: str):
    lines.append(str(msg))
    OUT.write_text("\n".join(lines), encoding="utf-8")


import httpx

from app.config import settings
from app.rag import vector_db
from app.rag.guide_catalog import GUIDE_CATALOG

# 1. 分块情况
log("== 分块情况 ==")
all_docs = []
for guide in GUIDE_CATALOG:
    text = guide.path.read_text(encoding="utf-8")
    docs = vector_db.split_markdown(text, guide.city)
    all_docs.extend(docs)
    log(f"{guide.city}: {len(docs)} 块")

lens = [len(d.page_content) for d in all_docs]
log(f"总块数: {len(all_docs)}, 最短: {min(lens)}, 最长: {max(lens)}")
empty = [i for i, d in enumerate(all_docs) if len(d.page_content.strip()) == 0]
log(f"空块索引: {empty}")
very_short = [(i, len(d.page_content)) for i, d in enumerate(all_docs) if len(d.page_content) < 5]
log(f"超短块: {very_short[:10]}")

# 2. 直接发全部文本测试
log("\n== 直接发送全部文本 ==")
texts = [d.page_content for d in all_docs]
resp = httpx.post(
    f"{settings.EMBED_BASE_URL.rstrip('/')}/embeddings",
    headers={"Authorization": f"Bearer {settings.EMBED_API_KEY}", "Content-Type": "application/json"},
    json={"model": settings.EMBED_MODEL_NAME, "input": texts},
    timeout=60,
)
log(f"状态: {resp.status_code}")
log(f"响应: {resp.text[:500]}")

# 3. 如果失败，二分定位：逐条发，找坏文本
if resp.status_code != 200:
    log("\n== 逐条发送定位 ==")
    for i, t in enumerate(texts):
        r = httpx.post(
            f"{settings.EMBED_BASE_URL.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {settings.EMBED_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.EMBED_MODEL_NAME, "input": [t]},
            timeout=30,
        )
        if r.status_code != 200:
            log(f"  坏块[{i}] 长度={len(t)}: {r.text[:200]}")
            log(f"    内容开头: {t[:80]!r}")
        # 只找前 3 个坏块就停
        if sum(1 for _ in [1]) > 0 and i > 40:
            break
