# ============================================
# RAG 在线阶段调试脚本（debug_rag_retrieval.py）
# 用法：
#   python backend/scripts/debug_rag_retrieval.py --city 西安 --query "西安美食推荐"
#   python backend/scripts/debug_rag_retrieval.py --case 0        # 用评估集第 N 条
# 输出：检索 query → 改写后 query → 召回片段 → rerank 分数与理由
# 原理：真实走完整在线链路（改写→召回→重排），绕过缓存看真实效果
# ============================================
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.tools import rag_tool
from app.rag import retriever, vector_db

EVAL_FILE = Path(__file__).resolve().parent.parent / "eval" / "rag_eval_cases.json"


def load_case(idx: int) -> dict:
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return cases[idx]


def main():
    parser = argparse.ArgumentParser(description="RAG 检索链路调试")
    parser.add_argument("--city", default="", help="目标城市（留空则从 case 读取）")
    parser.add_argument("--query", default="", help="用户原始查询")
    parser.add_argument("--case", type=int, default=-1, help="使用评估集第 N 条（优先级高于 city/query）")
    args = parser.parse_args()

    if args.case >= 0:
        case = load_case(args.case)
        city, query = case["city"], case["query"]
        print(f"评估样例 #{args.case}: [{case['category']}] {query}")
    else:
        city, query = args.city, args.query
        if not query:
            print("请提供 --query，或用 --case N 指定评估样例")
            sys.exit(1)

    print("=" * 60)
    print(f"① 用户原始查询: {query}")

    # 1) 改写
    t0 = time.time()
    rewritten = rag_tool.rewrite_query(f"{city} 旅行 {query}", city=city)
    print(f"② Query Rewrite: {rewritten['query']}（耗时 {(time.time()-t0)*1000:.0f}ms，关键词 {rewritten.get('keywords')}）")

    # 2) 召回（绕过缓存看原始召回）
    docs = vector_db.retrieve(rewritten["query"], top_k=8, city=city)
    print(f"③ 向量召回: {len(docs)} 条")
    for i, d in enumerate(docs[:8]):
        print(f"   [{i}] ({d.metadata.get('city', '?')}) {d.page_content[:80]}")

    # 3) 重排（绕过缓存）
    t0 = time.time()
    hits = retriever.retrieve_and_rerank(rewritten["query"], city=city, use_cache=False)
    print(f"④ 重排结果（耗时 {(time.time()-t0)*1000:.0f}ms）:")
    for h in hits:
        print(f"   score={h['score']} city={h['city']} reason={h['reason'][:40]}")
        print(f"     内容: {h['content'][:120]}")

    # 4) 注入上下文预览
    ctx = retriever.format_context(hits)
    print(f"⑤ 注入 LLM 的上下文共 {len(ctx)} 字，开头：")
    print(ctx[:300])


if __name__ == "__main__":
    main()
