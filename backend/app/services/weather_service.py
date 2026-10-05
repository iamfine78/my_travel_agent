# ============================================
# 天气服务（高德天气接口 + Redis 缓存）
# 职责：给前端提供城市天气预报
# 原理/坑：
#   - 高德天气接口 city 参数直接传城市名有歧义（"西安"会被解析成
#     黑龙江牡丹江的西安区！），必须先地理编码拿到 adcode 再查
#   - extensions=all 返回逐日预报（forecasts，3天）+ 实时（lives）
#   - 结果缓存 Redis（TTL 3 小时），天气短期内基本不变
# ============================================
import logging

import httpx

from app.config import settings
from app.services import cache_service

logger = logging.getLogger(__name__)

WEATHER_TTL = 3 * 3600  # 天气缓存 3 小时


def _amap_get(endpoint: str, params: dict) -> dict:
    """高德 Web 服务统一请求封装。"""
    params["key"] = settings.AMAP_WEB_KEY
    resp = httpx.get(f"{settings.AMAP_BASE_URL}/{endpoint}", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_adcode(city: str) -> str | None:
    """地理编码：城市名 → adcode（行政区划代码，如 西安→610100）。

    高德天气接口用 adcode 最稳，避免同名行政区歧义。
    """
    data = _amap_get("geocode/geo", {"address": city, "city": city})
    geocodes = data.get("geocodes") or []
    if geocodes:
        return geocodes[0].get("adcode")
    return None


def get_weather(city: str) -> dict | None:
    """查询城市天气，返回 3 天预报 + 实时信息；失败返回 None。"""
    # 1. 缓存
    cache_key = f"weather:{city}"
    cached = cache_service.cache_get(cache_key)
    if cached:
        return cached

    # 2. 解析 adcode（城市歧义修复）
    adcode = get_adcode(city)
    if not adcode:
        logger.warning(f"地理编码失败: {city}")
        return None

    # 3. 查天气：extensions=all 给逐日预报（forecasts）；extensions=base 给实时（lives）
    #    两个参数返回的字段不同，需要各查一次再合并
    data_all = _amap_get("weather/weatherInfo", {"city": adcode, "extensions": "all"})
    if data_all.get("status") != "1":
        logger.warning(f"高德天气失败: {data_all.get('info')}")
        return None

    data_live = _amap_get("weather/weatherInfo", {"city": adcode, "extensions": "base"})
    live = {}
    if data_live.get("status") == "1":
        live = (data_live.get("lives") or [{}])[0]

    forecast = (data_all.get("forecasts") or [{}])[0]
    result = {
        "city": forecast.get("city", city),
        "adcode": adcode,
        "live": live,
        "forecasts": forecast.get("casts") or [],
    }

    # 4. 缓存后返回
    cache_service.cache_set(cache_key, result, ttl=WEATHER_TTL)
    return result
