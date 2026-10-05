# ============================================
# 知识一致性校验：攻略、规则与评估配置
# 职责：启动/入库前检查 RAG 语料是否完备，避免带病运行
# 原理：把"应该有"的东西逐项检查，返回问题清单
# ============================================
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def validate() -> list[str]:
    """返回所有问题列表；空列表 = 一切正常。"""
    problems: list[str] = []
    data_dir = Path(settings.BASE_DIR) / "data"

    # 1. 攻略文件检查
    from app.rag.guide_catalog import GUIDE_CATALOG

    for guide in GUIDE_CATALOG:
        if not guide.exists:
            problems.append(f"攻略文件缺失: {guide.file_name}（城市 {guide.city}）")

    # 2. 攻略内容基本结构检查（应包含景点标题）
    for guide in GUIDE_CATALOG:
        if guide.exists:
            text = guide.path.read_text(encoding="utf-8")
            if "## " not in text:
                problems.append(f"攻略缺少二级标题结构: {guide.file_name}")
            if "门票" not in text and "地址" not in text:
                problems.append(f"攻略缺少门票/地址信息: {guide.file_name}")

    # 3. 检索规则文件检查
    rules_path = data_dir / "retrieval_rules.json"
    if not rules_path.exists():
        problems.append("缺失 data/retrieval_rules.json")
    else:
        try:
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            if not isinstance(rules.get("rules"), list) or len(rules["rules"]) == 0:
                problems.append("retrieval_rules.json 结构异常或为空")
        except json.JSONDecodeError:
            problems.append("retrieval_rules.json 不是合法 JSON")

    # 4. 关键配置检查（缺 key 不影响启动，但影响能力）
    if not settings.DEEPSEEK_API_KEY:
        problems.append("缺少 DEEPSEEK_API_KEY（LLM 不可用）")
    if not settings.EMBED_API_KEY:
        problems.append("缺少 EMBED_API_KEY（RAG 向量化不可用）")

    return problems


def validate_and_report(verbose: bool = True) -> bool:
    """执行校验并打印报告；返回是否全部通过。"""
    problems = validate()
    if verbose:
        print("=" * 40)
        print("RAG 知识一致性校验")
        print("=" * 40)
        if not problems:
            print("✅ 全部通过：攻略、规则、配置均就绪")
        else:
            for p in problems:
                print(f"❌ {p}")
    return len(problems) == 0
