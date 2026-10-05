# 验证营业时间补全：enrich 后 activity 带 open_time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import map_service

acts = [
    {"place": "秦始皇兵马俑博物馆"},
    {"place": "回民街"},
    {"place": "大唐芙蓉园"},
]
for a in acts:
    map_service.enrich_activity(a, "西安")
    print(f"{a['place']} → open_time={a.get('open_time', '(空)')!r}")
