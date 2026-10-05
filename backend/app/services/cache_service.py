# ============================================
# Redis 缓存服务（短期高频查询的缓存层）
# 职责：Redis 客户端懒加载、JSON 缓存读写、Redis 不可用时的优雅降级
# 原理：
#   - 懒加载：import 时不连 Redis，第一次用时才创建连接（启动快）
#   - 降级：Redis 连不上时返回 None / False，业务方直接查外部服务，
#           系统"只变慢、不崩"
#   - 所有 key 统一加 trip_planner: 前缀，避免与其他应用冲突
# 用法：
#   cache_service.cache_get("weather:西安")  → 命中返回对象/未命中返回 None
#   cache_service.cache_set("weather:西安", {...}, ttl=3600)
# ============================================
import json
import logging
from typing import Any, Optional

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# 全局客户端，懒加载。False 表示"已确认 Redis 不可用"，避免每次重试
_client: Any = None


def _get_client() -> Optional[redis.Redis]:
    """惰性创建 Redis 客户端；失败标记为不可用。"""
    global _client
    if _client is None:
        try:
            client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2,
                protocol=2,  # RESP2 协议：兼容 Redis 5.0（Windows 原生版），避免 HELLO 报错
            )
            client.ping()  # 真实发一次 PING 确认连通
            _client = client
        except Exception as e:
            _client = False  # Redis 不可用，后续调用直接跳过
            logger.warning(f"Redis 不可用，进入降级模式: {e}")
    # 注意：返回 None 表示不可用；返回客户端表示可用
    return _client if _client is not False else None


def _key(name: str) -> str:
    """统一加前缀，如 trip_planner:weather:西安"""
    return f"{settings.REDIS_KEY_PREFIX}:{name}"


def cache_get(name: str) -> Optional[Any]:
    """读缓存：命中返回 Python 对象，未命中/异常返回 None。"""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_key(name))
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"缓存读取失败 {name}: {e}")
        return None


def cache_set(name: str, value: Any, ttl: Optional[int] = None) -> bool:
    """写缓存：成功返回 True；Redis 不可用或失败返回 False。"""
    client = _get_client()
    if client is None:
        return False
    try:
        client.set(
            _key(name),
            json.dumps(value, ensure_ascii=False),
            ex=ttl or settings.REDIS_TTL_DEFAULT,
        )
        return True
    except Exception as e:
        logger.warning(f"缓存写入失败 {name}: {e}")
        return False


def cache_delete(name: str) -> bool:
    """删除缓存（数据变更后调用，保证新鲜度）。"""
    client = _get_client()
    if client is None:
        return False
    try:
        client.delete(_key(name))
        return True
    except Exception:
        return False
