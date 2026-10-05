# ============================================
# 探针：确认 dashscope 精排（rerank）端点的请求/响应形状
# 为什么先探针：rerank 不在 OpenAI 兼容协议下，端点和请求体与 chat/embeddings
#   都不同，凭记忆写容易错。先用最小请求打一次真实接口，确认字段名再接线。
# 用法：.venv\Scripts\python.exe -X utf8 backend/scripts/probe_rerank_api.py [模型名]
# 默认模型：qwen3-rerank（可用参数覆盖，或设环境变量 RERANK_MODEL）
# 注意：会消耗极少量额度；不会打印任何密钥。
# ============================================
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else (settings.RERANK_MODEL or "qwen3-rerank")
    url = settings.RERANK_API_URL
    key = settings.RERANK_API_KEY

    print(f"端点 : {url}")
    print(f"模型 : {model}")
    print(f"密钥 : {'已配置 (长度 %d)' % len(key) if key else '❌ 未配置 (EMBED_API_KEY / RERANK_API_KEY)'}")
    if not key:
        return 1

    query = "西安 人文 历史 景点"
    documents = [
        "西安城墙·永宁门：明代城墙，可骑行环城，门票 54 元。",
        "成都火锅：牛油锅底配毛肚鸭肠，人均 80 元。",
        "陕西历史博物馆：国宝云集，需提前预约，免费开放。",
    ]

    payload = {
        "model": model,
        "input": {"query": query, "documents": documents},
        "parameters": {"return_documents": False, "top_n": 3},
    }

    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except Exception as e:
        print(f"\n❌ 请求失败（网络/代理?）: {e}")
        return 1

    print(f"\nHTTP {resp.status_code}")
    try:
        data = resp.json()
    except Exception:
        print("响应非 JSON：", resp.text[:500])
        return 1

    # 只打印结构，避免把整段无关内容刷屏
    print("顶层键 :", sorted(data.keys()))
    out = data.get("output") or {}
    print("output 键:", sorted(out.keys()) if isinstance(out, dict) else type(out).__name__)
    results = out.get("results") if isinstance(out, dict) else None
    if results:
        print("results[0] 键:", sorted(results[0].keys()))
        print("results 预览:", json.dumps(results[:3], ensure_ascii=False)[:400])
        print("\n✅ 端点与字段形状可用，可据此实现 _dashscope_rerank")
        return 0

    print("\n⚠️ 未在 output.results 找到结果，完整响应：")
    print(json.dumps(data, ensure_ascii=False)[:800])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
