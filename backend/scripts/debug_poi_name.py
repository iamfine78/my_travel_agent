# 验证：复杂名称 POI 匹配问题（"武康路—安福路梧桐区"）
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re
from app.services import map_service

NAME = "武康路—安福路梧桐区"

print("== 1. 原名称搜索 ==")
pois = map_service.search_poi(NAME, "上海", limit=3)
if pois:
    for p in pois[:3]:
        print(f"  {p['name']} | {p['location']} | {p['address'][:30]}")
else:
    print("  ❌ 无结果")

print("== 2. 清洗后搜索（去掉特殊符号）==")
cleaned = re.sub(r"[（）()—–\-·/／]", "", NAME)
print(f"  清洗名: {cleaned}")
pois2 = map_service.search_poi(cleaned, "上海", limit=3)
if pois2:
    for p in pois2[:3]:
        print(f"  {p['name']} | {p['location']} | {p['address'][:30]}")
else:
    print("  ❌ 无结果")

print("== 3. 再兜底：去掉括号内容只留核心词 ==")
core = "武康路"
pois3 = map_service.search_poi(core, "上海", limit=3)
if pois3:
    for p in pois3[:3]:
        print(f"  {p['name']} | {p['location']} | {p['address'][:30]}")
else:
    print("  ❌ 无结果")
