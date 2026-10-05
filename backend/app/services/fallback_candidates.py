# ============================================
# 攻略候选提取（fallback_candidates）
# 职责：A 级城市 RAG 检索为空/不足时，从攻略原文提取真实候选给 Planner，
#       避免 LLM 自由发挥编造地点
# 原理（启发式）：
#   攻略 md 里用 "- 名称：描述" 或 "- 名称——描述" 列出推荐点，
#   按行首 "-" 提取项目名（冒号/破折号前的内容）
# ============================================
import logging
import re

from app.services import city_registry_service

logger = logging.getLogger(__name__)


def extract_from_guide(city: str, limit: int = 15) -> list[str]:
    """从攻略原文提取候选地名（去重、限条数）。"""
    guide = city_registry_service.get_guide(city)
    if guide is None or not guide.exists:
        return []
    text = guide.path.read_text(encoding="utf-8")

    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        # 匹配 "- 名称：描述" / "- 名称——描述" / "- **名称**：描述"
        m = re.match(r"^[-*]\s*(?:\*\*)?(.+?)(?:\*\*)?\s*[：:—\-—]", line)
        if not m:
            m = re.match(r"^[-*]\s*(?:\*\*)?([^\*：:]{2,20})(?:\*\*)?$", line)
        if not m:
            continue
        name = m.group(1).strip()
        # 过滤明显不是地点的词（数字、空白、长描述）
        if not name or name in seen or len(name) < 2 or re.match(r"^[\d\s]+$", name):
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def format_guide_candidates(names: list[str], city: str) -> str:
    """把攻略候选格式化成给 LLM 的文本。"""
    if not names:
        return ""
    lines = [f"以下地点来自《{city}本地攻略》（真实收录），优先考虑："]
    for i, n in enumerate(names, 1):
        lines.append(f"{i}. {n}")
    return "\n".join(lines)
