# ============================================
# 攻略候选提取（fallback_candidates）
# 职责：A 级城市 RAG 检索为空/不足时，从攻略原文提取真实候选给 Planner，
#       避免 LLM 自由发挥编造地点
# 原理（启发式）：
#   攻略 md 里景点写成三级标题（"### 名称（括注）"），优先按标题提取；
#   没有标题结构时才退回解析 "- 名称：描述" 行
#   （本项目语料里 "-" 行其实是「- 地址：…」这类字段，直接抽会抽到字段名）
# ============================================
import logging
import re

from app.services import city_registry_service

logger = logging.getLogger(__name__)


def extract_from_guide(city: str, limit: int = 15) -> list[str]:
    """从攻略原文提取候选地名（去重、限条数）。

    语料里景点写成三级标题（如 `### 秦始皇兵马俑博物馆（临潼）`），
    所以以标题为主要来源；某份攻略没有标题结构时，才退回解析 `- 名称：描述` 行。
    """
    guide = city_registry_service.get_guide(city)
    if guide is None or not guide.exists:
        return []
    text = guide.path.read_text(encoding="utf-8")
    return _extract_heading_names(text, limit) or _extract_bullet_names(text, limit)


def _extract_heading_names(text: str, limit: int) -> list[str]:
    """从 ### / #### 标题提取地名（当前语料的景点格式）。"""
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^#{3,4}\s+(.+)$", line.strip())
        if not m:
            continue
        # 去掉尾部括注：「秦始皇兵马俑博物馆（临潼）」→「秦始皇兵马俑博物馆」
        name = re.sub(r"[（(][^）)]*[）)]\s*$", "", m.group(1)).strip()
        if not name or name in seen or len(name) < 2:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _extract_bullet_names(text: str, limit: int) -> list[str]:
    """兜底：从 "- 名称：描述" 行提取（仅在攻略没有标题结构时使用）。"""
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
