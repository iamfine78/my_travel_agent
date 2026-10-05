# ============================================
# 生成示例行程单：真实 LLM 生成 → 导出 Markdown + PDF 到项目目录
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

# 用真实服务器流程：TestClient 完整走一遍 API（plan → save → export）
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)
OUT_DIR = Path(r"C:\Users\19674\PycharmProjects\pythonProject2")

# 1. 生成行程（真实 LLM + RAG + 高德）
r = client.post(
    "/api/trip/plan",
    json={"destination": "西安", "days": 2, "budget": 1200, "companions": "情侣", "preferences": "人文+美食"},
)
assert r.status_code == 200, r.text[:300]
body = r.json()
print(f"生成成功 | 来源: {body['sources']}")

# 2. 保存历史
r2 = client.post(
    "/api/trip",
    json={
        "destination": "西安",
        "summary": body["itinerary"].get("summary", ""),
        "itinerary_json": body["itinerary"],
    },
)
assert r2.status_code == 201
trip_id = r2.json()["trip_id"]
print(f"已保存历史 trip_id={trip_id[:8]}")

# 3. 导出 Markdown
r3 = client.post(f"/api/export/{trip_id}?format=md")
(OUT_DIR / "示例行程单.md").write_text(r3.text, encoding="utf-8")
print(f"✅ Markdown 已导出: 示例行程单.md ({len(r3.text)} 字符)")

# 4. 导出 PDF
r4 = client.post(f"/api/export/{trip_id}?format=pdf")
(OUT_DIR / "示例行程单.pdf").write_bytes(r4.content)
print(f"✅ PDF 已导出: 示例行程单.pdf ({len(r4.content)} 字节)")

# 5. 清理历史（示例文件保留，历史记录删掉避免占库）
client.delete(f"/api/trip/{trip_id}")
print("测试历史记录已清理")
