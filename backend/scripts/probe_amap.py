# ============================================
# 高德 API 连通性探测（只读测试）
# 测试：天气接口 + 地理编码 + POI 搜索 + 静态图
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings

BASE = settings.AMAP_BASE_URL
KEY = settings.AMAP_WEB_KEY
OUT = Path(__file__).resolve().parent / "_amap_probe.txt"
lines = []


def log(msg: str):
    lines.append(str(msg))
    OUT.write_text("\n".join(lines), encoding="utf-8")


if not KEY:
    log("❌ AMAP_WEB_KEY 未配置")
    sys.exit(1)

log(f"高德 Web Key: {KEY[:6]}...（已配置）")

# 1. 天气接口
log("\n== 1. 天气接口 GET /v3/weather/weatherInfo ==")
r = httpx.get(f"{BASE}/weather/weatherInfo", params={"city": "西安", "key": KEY}, timeout=20)
log(f"  状态: {r.status_code}")
try:
    d = r.json()
    if d.get("status") == "1":
        casts = d.get("forecasts", [{}])[0].get("casts", [])
        log(f"  ✅ 天气可用: {d['forecasts'][0]['city']} 今日 {casts[0]['dayweather']} {casts[0]['daytemp']}~{casts[0]['nighttemp']}℃")
    else:
        log(f"  ❌ 高德返回错误: {d.get('info')}")
except Exception as e:
    log(f"  ❌ 解析失败: {e} | {r.text[:200]}")

# 2. 地理编码
log("\n== 2. 地理编码 GET /v3/geocode/geo ==")
r = httpx.get(f"{BASE}/geocode/geo", params={"address": "西安城墙", "city": "西安", "key": KEY}, timeout=20)
d = r.json()
if d.get("status") == "1" and d.get("geocodes"):
    g = d["geocodes"][0]
    log(f"  ✅ 地理编码: {g['formatted_address']} | 坐标 {g.get('location')}")
else:
    log(f"  ❌ 失败: {d.get('info')}")

# 3. POI 搜索（周边）
log("\n== 3. POI 搜索 GET /v3/place/text ==")
r = httpx.get(f"{BASE}/place/text", params={"keywords": "秦始皇兵马俑", "city": "西安", "key": KEY}, timeout=20)
d = r.json()
if d.get("status") == "1" and d.get("pois"):
    p = d["pois"][0]
    log(f"  ✅ POI: {p['name']} | 类型 {p.get('type')} | POI_ID {p.get('id')} | 坐标 {p.get('location')}")
    log(f"    地址: {p.get('address')} | 图片字段存在: {'photos' in p and len(p.get('photos') or []) > 0}")
else:
    log(f"  ❌ 失败: {d.get('info')}")
