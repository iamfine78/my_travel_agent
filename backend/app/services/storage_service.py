# ============================================
# SQLite 存储服务（长期业务数据：用户保存的行程）
# 作用：封装对 trip_records 表的增删查改，供 trip 路由调用
# 原理：
#   - create_engine: 创建数据库连接引擎（sqlite 文件不存在会自动建）
#   - Base.metadata.create_all(engine): 首次启动自动建表
#   - Session: 每次操作开一个会话，提交后关闭（with 语句保证释放）
# ============================================
import json
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.db_models import Base, TripRecord

# 创建引擎 + 会话工厂
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 允许多线程访问（FastAPI 异步场景需要）
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """应用启动时调用：确保表存在。"""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    """上下文管理器：自动开/关会话。用法：
       with get_session() as db: db.add(...); db.commit()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- 增删查改 ----------
def create_trip(destination: str, summary: str = "", itinerary: dict | None = None) -> TripRecord:
    """保存一条新行程，返回带 trip_id 的记录。"""
    record = TripRecord(
        destination=destination,
        summary=summary,
        itinerary_json=json.dumps(itinerary or {}, ensure_ascii=False),
    )
    with get_session() as db:
        db.add(record)
        db.commit()
        db.refresh(record)  # 拿到数据库生成的 trip_id / created_at
    return record


def get_trip(trip_id: str) -> Optional[TripRecord]:
    """按 trip_id 查一条行程；不存在返回 None。"""
    with get_session() as db:
        return db.get(TripRecord, trip_id)


def list_trips(limit: int = 20, offset: int = 0) -> list[TripRecord]:
    """历史列表：按创建时间倒序（最新在前），支持分页。"""
    with get_session() as db:
        return (
            db.query(TripRecord)
            .order_by(TripRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def count_trips() -> int:
    """历史行程总数（与分页无关的真实计数，供列表接口的 total 字段用）。"""
    with get_session() as db:
        return db.query(TripRecord).count()


def delete_trip(trip_id: str) -> bool:
    """删除一条行程；返回是否真的删掉了。"""
    with get_session() as db:
        rec = db.get(TripRecord, trip_id)
        if rec is None:
            return False
        db.delete(rec)
        db.commit()
        return True


def update_trip(trip_id: str, itinerary: dict) -> Optional[TripRecord]:
    """用新的 itinerary 覆盖旧数据（用于补全旧行程的地理信息），返回更新后的记录。"""
    with get_session() as db:
        rec = db.get(TripRecord, trip_id)
        if rec is None:
            return None
        rec.itinerary_json = json.dumps(itinerary, ensure_ascii=False)
        db.commit()
        db.refresh(rec)
    return rec


def to_record_out(record: TripRecord) -> dict:
    """把 ORM 对象转成响应 dict（itinerary_json 字符串 → 字典）。"""
    return {
        "trip_id": record.trip_id,
        "destination": record.destination,
        "summary": record.summary,
        "itinerary": json.loads(record.itinerary_json or "{}"),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
