# ============================================
# RAG 检索效果评估（evaluate_rag_retrieval.py）
# 用法：
#   python backend/scripts/evaluate_rag_retrieval.py            # 跑全部 18 条（较慢，需 LLM）
#   python backend/scripts/evaluate_rag_retrieval.py --limit 3  # 快速验证前 3 条
# 指标口径：
#   Top1 Hit     ：第 1 条结果包含任一期望词 → 1
#   Top3 Hit     ：前 3 条包含任一期望词 → 1
#   MRR          ：首个命中结果的 1/排名（1-based）；全未命中记 0
#   Noise Rate   ：不含任何期望词的返回结果占比（垃圾结果比例）
#   Latency      ：完整链路（改写+召回+重排，无缓存）平均耗时 ms
#   Cross-dest. Pollution：返回结果中城市 ≠ 目标城市的占比（应≈0，验证 metadata 过滤）
# ============================================
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.tools import rag_tool
from app.rag import retriever

EVAL_FILE = Path(__file__).resolve().parent.parent / "eval" / "rag_eval_cases.json"


def hits_any(content: str, terms: list[str]) -> bool:
    return any(t in content for t in terms)


def evaluate_one(case: dict) -> dict:
    t0 = time.time()
    rewritten = rag_tool.rewrite_query(f"{case['city']} 旅行 {case['query']}", city=case["city"])
    results = retriever.retrieve_and_rerank(rewritten["query"], city=case["city"], use_cache=False)
    latency_ms = (time.time() - t0) * 1000

    terms = case["expected_terms"]
    n = len(results)
    top1 = hits_any(results[0]["content"], terms) if n else False
    top3 = any(hits_any(h["content"], terms) for h in results[:3]) if n else False

    # MRR：首个命中结果的 1/rank
    mrr = 0.0
    for i, h in enumerate(results[:3], 1):
        if hits_any(h["content"], terms):
            mrr = 1.0 / i
            break

    # Noise Rate：不含任何期望词的占比
    noise = sum(1 for h in results if not hits_any(h["content"], terms)) / n if n else 0.0

    # Cross-destination Pollution：城市不匹配的占比
    pollution = sum(1 for h in results if h["city"] != case["city"]) / n if n else 0.0

    return {
        "id": case["id"],
        "category": case["category"],
        "n": n,
        "top1": int(top1),
        "top3": int(top3),
        "mrr": round(mrr, 3),
        "noise": round(noise, 2),
        "latency_ms": round(latency_ms),
        "pollution": round(pollution, 3),
    }


def main():
    parser = argparse.ArgumentParser(description="RAG 检索效果量化评估")
    parser.add_argument("--limit", type=int, default=0, help="只评估前 N 条（0=全部）")
    args = parser.parse_args()

    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    print(f"共 {len(cases)} 条评估样例，开始（完整链路，无缓存）…\n")
    rows = []
    for case in cases:
        r = evaluate_one(case)
        rows.append(r)
        flag = "✔" if r["top3"] else "✘"
        print(f"{flag} {r['id']:<10} [{r['category']}] top1={r['top1']} top3={r['top3']} "
              f"mrr={r['mrr']} noise={r['noise']} lat={r['latency_ms']}ms poll={r['pollution']}")

    # 汇总
    n = len(rows)
    if not n:
        print("无样例")
        return
    agg = {
        "Top1 Hit Rate": f"{sum(r['top1'] for r in rows) / n * 100:.1f}%",
        "Top3 Hit Rate": f"{sum(r['top3'] for r in rows) / n * 100:.1f}%",
        "MRR": f"{sum(r['mrr'] for r in rows) / n:.3f}",
        "Noise Rate": f"{sum(r['noise'] for r in rows) / n * 100:.1f}%",
        "Avg Latency": f"{sum(r['latency_ms'] for r in rows) / n:.0f} ms",
        "Cross-dest Pollution": f"{sum(r['pollution'] for r in rows) / n * 100:.2f}%",
    }
    print("\n" + "=" * 40)
    print("汇总指标：")
    for k, v in agg.items():
        print(f"  {k:<22} {v}")


if __name__ == "__main__":
    main()
