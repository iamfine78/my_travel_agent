# ============================================
# 向量库：文档切片、Chroma 入库与检索
# 职责：把 Markdown 攻略切成语义块 → 向量化 → 存 Chroma；
#       检索时按查询向量召回 top-k
# 原理：
#   - 切片：攻略按 "## 标题" 分块（每块是一个语义单元），
#     块太大时再按字符切，保证长度可控
#   - 向量化：dashscope text-embedding-v3（OpenAI 兼容接口）
#   - 存储：langchain_chroma.Chroma 持久化到 backend/data/chroma_db
# ============================================
import logging
import re
import uuid

from langchain_core.documents import Document
from langchain_chroma import Chroma

from app.config import settings
from app.rag.embeddings import HttpEmbeddings

logger = logging.getLogger(__name__)

# ---------- 1. 切片 ----------
def split_markdown(text: str, city: str, max_chars: int = 600) -> list[Document]:
    """把一篇攻略按标题切成文档块。

    - 按 '## ' 与 '### ' 标题切分，标题作为块的上下文保留
    - 超过 max_chars 的块继续按段落切，避免超长向量
    - 每块带上 city 元数据（检索时可按城市过滤）
    """
    # 正则切分：找到所有 '##' 或 '###' 标题及其后内容
    lines = text.split("\n")
    blocks: list[str] = []
    current = ""
    current_title = ""

    def flush():
        nonlocal current, current_title
        if current.strip():
            header = f"{current_title}\n" if current_title else ""
            blocks.append(header + current.strip())
        current = ""
        current_title = ""

    for line in lines:
        if line.startswith("## "):
            flush()
            current_title = line.strip()
        elif line.startswith("### "):
            # 三级标题并入当前块内容（不另起块，避免太碎）
            current += line.strip() + "\n"
        else:
            current += line + "\n"
    flush()

    # 超长块按段落再切
    docs: list[Document] = []
    for block in blocks:
        if len(block) <= max_chars:
            docs.append(Document(page_content=block, metadata={"city": city}))
        else:
            # 按空行段落切，递归合并到 max_chars 内
            paras = [p.strip() for p in block.split("\n\n") if p.strip()]
            chunk = ""
            for p in paras:
                if len(chunk) + len(p) <= max_chars:
                    chunk += p + "\n"
                else:
                    if chunk.strip():
                        docs.append(Document(page_content=chunk.strip(), metadata={"city": city}))
                    chunk = p + "\n"
            if chunk.strip():
                docs.append(Document(page_content=chunk.strip(), metadata={"city": city}))
    return docs


# ---------- 2. 嵌入模型（懒加载，httpx 自建客户端） ----------
_embeddings = None


def get_embeddings() -> HttpEmbeddings:
    """dashscope MaaS 嵌入（OpenAI 兼容端点，httpx 直连）。"""
    global _embeddings
    if _embeddings is None:
        _embeddings = HttpEmbeddings(
            base_url=settings.EMBED_BASE_URL,
            api_key=settings.EMBED_API_KEY,
            model=settings.EMBED_MODEL_NAME,
        )
    return _embeddings


# ---------- 3. Chroma 存储 ----------
_collection = None


def get_collection() -> Chroma:
    """获取（或创建）持久化集合。"""
    global _collection
    if _collection is None:
        _collection = Chroma(
            collection_name=settings.CHROMA_COLLECTION,
            embedding_function=get_embeddings(),
            persist_directory=settings.CHROMA_DIR,
        )
    return _collection


# ---------- 4. 入库 ----------
def index_guides(force: bool = False) -> int:
    """把 data/ 下全部攻略切片入库。已入库跳过（force=True 强制重建）。

    返回入库的文档块数。
    """
    from app.rag.guide_catalog import GUIDE_CATALOG

    collection = get_collection()
    if not force:
        # 已入库的攻略块，跳过（幂等：重复运行不重复添加）
        existing = collection.get()["ids"]
        if existing:
            logger.info(f"向量库已有 {len(existing)} 块，跳过入库（force=True 可重建）")
            return len(existing)

    all_docs: list[Document] = []
    for guide in GUIDE_CATALOG:
        text = guide.path.read_text(encoding="utf-8") if guide.exists else ""
        if not text:
            logger.warning(f"攻略缺失: {guide.file_name}")
            continue
        docs = split_markdown(text, guide.city)
        all_docs.extend(docs)
        logger.info(f"  {guide.city}: {len(docs)} 块")

    # 先清空旧数据再入库（重建模式）
    if force:
        try:
            collection.delete_collection()
            _collection = None
            collection = get_collection()
        except Exception as e:
            logger.warning(f"清空旧集合失败: {e}")

    ids = [uuid.uuid4().hex for _ in all_docs]
    collection.add_documents(all_docs, ids=ids)
    logger.info(f"入库完成：共 {len(all_docs)} 块")
    return len(all_docs)


# ---------- 5. 检索 ----------
def retrieve(query: str, top_k: int = None, city: str | None = None) -> list[Document]:
    """向量检索：默认按全局检索；city 非空时按城市过滤（A 级城市限定本城攻略）。"""
    k = top_k or settings.RAG_TOP_K
    collection = get_collection()
    if city:
        # filter 条件：只在本城攻略里找，避免跨目的地污染
        return collection.similarity_search(query, k=k, filter={"city": city})
    return collection.similarity_search(query, k=k)
