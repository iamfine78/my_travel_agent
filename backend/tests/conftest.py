# ============================================
# pytest 公共夹具（conftest）
# 原则：单元测试不依赖网络 / LLM / Redis / 真实数据库——
#   需要外部能力的用「假客户端」或 monkeypatch 顶替，保证离线可重复运行。
# ============================================
import sys
from pathlib import Path

import pytest

# 让测试能 import app.*（backend/ 加入 sys.path；tests 是包，pytest 一般已自动处理，这里显式兜底）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def sample_itinerary() -> dict:
    """一份最小可用行程（2 天，无图片 URL，避免导出时触发网络下载）。"""
    return {
        "destination": "西安",
        "summary": "西安两日人文美食之旅",
        "days": [
            {
                "day": 1,
                "date_hint": "第1天",
                "morning": [
                    {"place": "秦始皇兵马俑博物馆", "description": "看一号坑",
                     "play_guide": "建议游玩 3 小时，先看一号坑", "poi_id": "B001", "cost": 120}
                ],
                "afternoon": [
                    {"place": "华清宫", "description": "温泉池遗址",
                     "play_guide": "建议 2 小时", "poi_id": "B002", "cost": 120}
                ],
                "evening": [
                    {"place": "回民街", "description": "小吃一条街",
                     "play_guide": "晚上人多，注意财物", "poi_id": "B003", "cost": "人均60元"}
                ],
                "meals": ["肉夹馍", "biangbiang面"],
                "lodging": "建议住钟楼附近，交通便利",
                "note": "兵马俑需提前预约",
            },
            {
                "day": 2,
                "date_hint": "第2天",
                "morning": [
                    {"place": "陕西历史博物馆", "description": "国宝云集",
                     "play_guide": "需提前预约，建议 3 小时", "poi_id": "B004", "cost": 0}
                ],
                "afternoon": [
                    {"place": "大雁塔", "description": "玄奘译经地",
                     "play_guide": "可登塔远眺", "poi_id": "B005", "cost": 50}
                ],
                "evening": [
                    {"place": "大唐不夜城", "description": "夜景步行街",
                     "play_guide": "晚上灯光最美", "poi_id": "B006", "cost": 0}
                ],
                "meals": ["葫芦头泡馍"],
                "lodging": "继续住钟楼附近",
                "note": "陕历博周一闭馆",
            },
        ],
        "budget_split": {"transport": 500, "lodging": 600, "food": 400, "tickets": 300, "other": 200},
        "tips": ["春秋早晚温差大，注意添衣"],
    }


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    """把 storage_service 指向临时 SQLite 文件，避免污染 backend/data/travel.db。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.db_models import Base
    from app.services import storage_service

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_travel.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # 模块级全局替换：get_session / init_db 都读这两个全局名
    monkeypatch.setattr(storage_service, "engine", engine)
    monkeypatch.setattr(storage_service, "SessionLocal", SessionLocal)
    yield storage_service


@pytest.fixture
def fake_cache(monkeypatch):
    """内存版假 Redis，让依赖缓存的服务（rag_tool / retriever / map）离线可测。"""
    from app.services import cache_service

    class FakeRedis:
        def __init__(self):
            self.store: dict[str, str] = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value
            return True

        def delete(self, key):
            self.store.pop(key, None)
            return 1

        def ping(self):
            return True

    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "_client", fake)
    return fake


@pytest.fixture
def client(tmp_storage):
    """FastAPI TestClient，数据库已指向临时库；lifespan 启动时建表。"""
    from fastapi.testclient import TestClient

    from app.api.main import app

    with TestClient(app) as c:
        yield c
