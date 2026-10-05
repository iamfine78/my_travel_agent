# ============================================
# Token 观测统计器（token_tracker）
# 职责：记录每次 LLM 调用的 token 消耗，按阶段分类：
#   rewrite（查询改写）/ rerank（重排）/ planner（行程生成）/ edit（行程编辑）
# 原理：
#   - langchain 响应里有 response_metadata.token_usage（prompt/completion/total）
#   - 统计器累加各阶段消耗，提供快照与"两次快照之差"（本次请求增量）
# 注意：这是进程级内存统计（个人项目够用），重启后清零；
#       已保存行程的 token 另存进 itinerary_json["_token_usage"] 长期保留
# ============================================

PHASES = ("rewrite", "rerank", "planner", "edit")


class TokenTracker:
    def __init__(self):
        self.usage = {p: {"prompt": 0, "completion": 0, "total": 0} for p in PHASES}
        self.requests = {p: 0 for p in PHASES}

    def record(self, phase: str, response_metadata: dict | None):
        """记录一次 LLM 调用的 token（从 langchain 响应元数据取）。"""
        if phase not in self.usage:
            return
        usage = (response_metadata or {}).get("token_usage", {})
        if not usage:
            return
        self.usage[phase]["prompt"] += int(usage.get("prompt_tokens", 0) or 0)
        self.usage[phase]["completion"] += int(usage.get("completion_tokens", 0) or 0)
        self.usage[phase]["total"] += int(usage.get("total_tokens", 0) or 0)
        self.requests[phase] += 1

    def snapshot(self) -> dict:
        """当前累计快照（各阶段明细 + 合计）。"""
        return {
            "by_phase": {p: dict(self.usage[p]) for p in PHASES},
            "requests": dict(self.requests),
            "total": sum(self.usage[p]["total"] for p in PHASES),
        }

    def diff(self, before: dict, after: dict) -> dict:
        """两次快照之差 = 本次请求的 token 增量（用于响应字段）。"""
        diff = {}
        for p in PHASES:
            delta = {
                "prompt": max(after["by_phase"][p]["prompt"] - before["by_phase"][p]["prompt"], 0),
                "completion": max(after["by_phase"][p]["completion"] - before["by_phase"][p]["completion"], 0),
            }
            delta["total"] = delta["prompt"] + delta["completion"]
            diff[p] = delta
        return diff


# 进程级单例：全项目共用
token_tracker = TokenTracker()
