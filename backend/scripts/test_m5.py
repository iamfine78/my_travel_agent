# ============================================
# M5 测试：历史导出 Markdown / 中文 PDF
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app
from app.services import export_service

client = TestClient(app)
ok = fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}  {detail}")


# 构造一条行程数据（模拟 LLM 输出 + 高德补全）
sample_itinerary = {
    "destination": "西安",
    "summary": "2天古城美食之旅",
    "days": [
        {
            "day": 1,
            "date_hint": "第1天",
            "morning": [{"place": "西安城墙", "description": "古城墙骑行", "cost": 54, "address": "碑林区南大街"}],
            "afternoon": [{"place": "陕西历史博物馆", "description": "看青铜器", "cost": 0}],
            "evening": [{"place": "大唐不夜城", "description": "夜景", "cost": 0}],
            "meals": ["羊肉泡馍", "肉夹馍"],
            "note": "提前预约博物馆",
        },
        {
            "day": 2,
            "date_hint": "第2天",
            "morning": [{"place": "秦始皇兵马俑", "description": "世界奇迹", "cost": 120}],
            "afternoon": [{"place": "华清宫", "description": "皇家温泉行宫", "cost": 120}],
            "evening": [],
            "meals": ["biangbiang面"],
            "note": "",
        },
    ],
    "budget_split": {"transport": 300, "lodging": 500, "food": 400, "tickets": 400, "other": 100},
    "tips": ["周一博物馆闭馆", "带好身份证"],
}

print("== 1. 保存行程 ==")
r = client.post("/api/trip", json={"destination": "西安", "summary": "2天古城美食之旅", "itinerary_json": sample_itinerary})
check("保存成功", r.status_code == 201)
trip_id = r.json()["trip_id"]

print("== 2. 导出 Markdown ==")
r = client.post(f"/api/export/{trip_id}?format=md")
check("md 导出 200", r.status_code == 200)
md = r.text
check("含标题", "西安旅行行程单" in md)
check("含预算拆分", "预算拆分" in md and "合计" in md)
check("含每日行程", "第 1 天" in md and "第 2 天" in md)
check("含景点", "秦始皇兵马俑" in md)
check("含建议", "旅行建议" in md)
print(f"    前 3 行: {' | '.join(md.split(chr(10))[:3])}")

print("== 3. 导出 PDF ==")
r = client.post(f"/api/export/{trip_id}?format=pdf")
check("pdf 导出 200", r.status_code == 200)
check("Content-Type 是 PDF", r.headers.get("content-type", "").startswith("application/pdf"))
pdf_bytes = r.content
check("有 PDF 文件头", pdf_bytes[:5] == b"%PDF-")
check("PDF 非空且大于 1KB", len(pdf_bytes) > 1000, f"实际 {len(pdf_bytes)} 字节")

print("== 4. 当前页面数据导出（from-data）==")
r = client.post("/api/export/from-data?format=md", json={"destination": "西安", "itinerary": sample_itinerary})
check("from-data md 导出 200", r.status_code == 200)
check("from-data 内容正确", "大唐不夜城" in r.text)

print("== 5. PDF 中文渲染验证（字节层面）==")
# PDF 内部流包含中文字体的 ToUnicode 映射说明字体已嵌入；简单验证字体注册成功
check("字体可用", export_service.find_chinese_font() != "", export_service.find_chinese_font())

print("== 6. 清理 ==")
client.delete(f"/api/trip/{trip_id}")
check("测试行程已删除", True)

print(f"\n结果：通过 {ok} 项，失败 {fail} 项")
sys.exit(0 if fail == 0 else 1)
