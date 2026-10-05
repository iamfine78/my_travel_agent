# ============================================
# 攻略入库脚本：把 data/*.md 切块向量化写入 Chroma
# 用法：
#   .venv\Scripts\python.exe -X utf8 backend/scripts/build_vector_db.py        # 增量（已入库跳过）
#   .venv\Scripts\python.exe -X utf8 backend/scripts/build_vector_db.py --force # 强制重建
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag import knowledge_validation, vector_db

if __name__ == "__main__":
    # 1. 先做一致性校验
    if not knowledge_validation.validate_and_report():
        print("\n存在未通过项，是否继续入库？（问题项可能影响检索质量）")
        if "--force" not in sys.argv:
            pass  # 继续执行（可改进为交互确认）

    force = "--force" in sys.argv
    print(f"\n开始入库（force={force}）...")
    count = vector_db.index_guides(force=force)
    print(f"✅ 入库完成，共 {count} 个文档块")
