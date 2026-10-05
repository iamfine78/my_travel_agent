# ============================================
# 数据表定义（SQLAlchemy 2.x 风格）
# 作用：定义"数据库里存什么"——一张 TripRecord 表存用户保存的行程
# 原理：ORM（对象关系映射）：Python 类 ↔ 数据库表。
#       Mapped[X] 是类型注解，mapped_column() 定义列。
#       SQLAlchemy 会根据这些定义自动建表。
# ============================================
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表的基类。SQLAlchemy 2.x 要求声明一个 Base。"""


class TripRecord(Base):
    """用户保存的完整旅行方案（长期业务数据，存 SQLite）。"""

    __tablename__ = "trip_records"

    # 主键：UUID 十六进制字符串（全局唯一，比自增 id 更安全）
    trip_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    # 目的地（如 "西安"），供历史列表快速展示
    destination: Mapped[str] = mapped_column(String(100), index=True)
    # 行程一句话摘要
    summary: Mapped[str] = mapped_column(String(500), default="")
    # 完整行程的 JSON 字符串（结构化行程全量存这里）
    # 用 Text 而不是 JSON 列：SQLite 的 JSON 支持有限，Text + json.dumps 最稳
    itinerary_json: Mapped[str] = mapped_column(Text, default="{}")

    # 创建/更新时间（UTC 存储，展示时再转本地时区）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        # 必须与 created_at 一样带时区：原来直接用 datetime.now（无 tz），
        # 会让同一行里两个时间字段一个 UTC 一个本地时间，比较时差 8 小时
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # 调试时打印友好
        return f"<TripRecord {self.trip_id} → {self.destination}>"
