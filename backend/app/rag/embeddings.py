# ============================================
# 自建嵌入客户端（httpx 实现，OpenAI 兼容格式）
# 为什么自写：langchain-openai 1.6.7 对阿里云 MaaS 端点的
#   input 封装不兼容（报 input.contents 错误）；而 httpx 直接
#   发 OpenAI 兼容格式已被实测可用（见 scripts/probe_embed_api.py）
# 原理：POST {base_url}/embeddings
#       body: {"model": 模型名, "input": [文本列表]}
#       返回: {"data": [{"embedding": [浮点数...]}, ...]}
# 实现 langchain 的 Embeddings 接口（embed_documents / embed_query），
# 让 Chroma 和 LangChain 都能直接用。
# ============================================
import logging
from typing import Any, Optional

import httpx
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class HttpEmbeddings(Embeddings):
    """用 httpx 直连 OpenAI 兼容嵌入端点。"""

    # 阿里云 MaaS 端点单次请求最多接受 10 条文本，超出报 400
    BATCH_SIZE = 10

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _post(self, texts: list[str]) -> list[list[float]]:
        """核心：按批次发 HTTP 请求，返回全部向量（顺序与输入一致）。"""
        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            resp = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": batch},
                timeout=self.timeout,
            )
            resp.raise_for_status()  # 非 2xx 直接抛异常（上层捕获降级）
            data = resp.json()
            # 每批返回的向量顺序与本批输入一一对应
            all_vecs.extend(item["embedding"] for item in data.get("data", []))
        return all_vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（LangChain 接口）。"""
        if not texts:
            return []
        try:
            return self._post(texts)
        except Exception as e:
            logger.warning(f"嵌入请求失败: {e}")
            raise

    def embed_query(self, text: str) -> list[float]:
        """单个查询向量化（检索时用）。"""
        return self.embed_documents([text])[0]

    # chromadb EmbeddingFunction 也常用 __call__(input: Documents)
    def __call__(self, input: Any) -> list[list[float]]:
        if isinstance(input, str):
            return self.embed_documents([input])
        return self.embed_documents(list(input))
