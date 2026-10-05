# 验证手册风 PDF：真实生成西安 2 天行程 → 导出 PDF 保存
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.api.main import app
from app.services.export_service import itinerary_to_pdf_bytes

client = TestClient(app)
r = client.post("/api/trip/plan", json={
    "destination": "西安", "days": 2, "budget": 800,
    "preferences": "节奏：轻松；旅行偏好：美食、夜景",
})
print("plan:", r.status_code)
body = r.json()
pdf_bytes = itinerary_to_pdf_bytes(body["itinerary"], body["destination"], body.get("weather"))
out = Path(__file__).parent / "manual_sample.pdf"
out.write_bytes(pdf_bytes)
print(f"PDF 生成: {len(pdf_bytes)} bytes -> {out}")
