# ============================================
# 高德地图服务（Web 服务 API + Redis 缓存）
# 职责：给行程补全真实地理信息——地址、经纬度、POI ID、
#       路线距离/耗时、景点图片；同时服务 B 级动态城市候选池
# 缓存：每个接口结果都缓存（TTL 12 小时），减少外部调用
# ============================================
import logging

import httpx

from app.config import settings
from app.services import cache_service

logger = logging.getLogger(__name__)

MAP_TTL = 12 * 3600  # 地图/POI 数据 12 小时缓存


def _amap_get(endpoint: str, params: dict) -> dict:
    params["key"] = settings.AMAP_WEB_KEY
    resp = httpx.get(f"{settings.AMAP_BASE_URL}/{endpoint}", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ---------- 1. 地理编码 ----------
def geocode(address: str, city: str = "") -> dict | None:
    """地址 → 经纬度。返回 {location, formatted_address, adcode}。"""
    cache_key = f"geocode:{city}:{address}"
    cached = cache_service.cache_get(cache_key)
    if cached:
        return cached

    params = {"address": address}
    if city:
        params["city"] = city
    data = _amap_get("geocode/geo", params)
    geocodes = data.get("geocodes") or []
    if not geocodes:
        return None
    g = geocodes[0]
    loc = g.get("location", "")
    if "," in loc:
        lng, lat = loc.split(",")
    else:
        lng, lat = "", ""
    result = {
        "lng": lng,
        "lat": lat,
        "location": loc,
        "formatted_address": g.get("formatted_address", ""),
        "adcode": g.get("adcode", ""),
    }
    cache_service.cache_set(cache_key, result, ttl=MAP_TTL)
    return result


# ---------- 2. POI 搜索 ----------
def search_poi(keywords: str, city: str, poi_type: str = "", limit: int = 10) -> list[dict]:
    """关键词搜索 POI（景点/餐饮/住宿）。返回列表，含 id/坐标/地址/图片。"""
    cache_key = f"poi:{city}:{keywords}:{poi_type}:{limit}"
    cached = cache_service.cache_get(cache_key)
    if cached:
        return cached

    params = {"keywords": keywords, "city": city, "offset": limit, "page": 1}
    if poi_type:
        params["types"] = poi_type
    data = _amap_get("place/text", params)
    pois = data.get("pois") or []

    result = []
    for p in pois:
        loc = p.get("location", "")
        lng, lat = loc.split(",") if "," in loc else ("", "")
        photos = p.get("photos") or []
        biz_ext = p.get("biz_ext") or {}
        result.append(
            {
                "poi_id": p.get("id", ""),
                "name": p.get("name", ""),
                "type": p.get("type", ""),
                "address": p.get("address", ""),
                "lng": lng,
                "lat": lat,
                "location": loc,
                "image_url": (photos[0].get("url", "") if photos else ""),
                "tel": p.get("tel", ""),
                # 营业时间在 biz_ext 里：open_time 纯时间 / opentime2 带星期
                "open_time": biz_ext.get("open_time") or biz_ext.get("opentime2") or "",
                "rating": biz_ext.get("rating", ""),  # 高德评分（如 4.8）
                "pname": p.get("pname", ""),   # 省
                "cityname": p.get("cityname", ""),
                "adname": p.get("adname", ""),  # 区县
            }
        )
    cache_service.cache_set(cache_key, result, ttl=MAP_TTL)
    return result


# ---------- 3. 路线规划（驾车距离/耗时） ----------
import time

def route_info(origin: str, dest: str) -> dict | None:
    """两点（经纬度）间驾车路线。返回 {distance, duration, cost}。

    注意：高德驾车接口偶发瞬时失败（无 paths / 网络抖动），
    失败时重试 1 次（间隔 0.6s），仍失败才返回 None。
    """
    cache_key = f"route:{origin}:{dest}"
    cached = cache_service.cache_get(cache_key)
    if cached:
        return cached

    for attempt in range(2):
        try:
            data = _amap_get(
                "direction/driving",
                {"origin": origin, "destination": dest, "strategy": 10},  # 策略10：速度优先
            )
            paths = data.get("route", {}).get("paths") or []
            if paths:
                p = paths[0]
                result = {
                    "distance": int(p.get("distance", 0)),  # 米
                    "duration": int(p.get("duration", 0)),  # 秒
                    "cost": p.get("tolls", 0),              # 过路费（元）
                }
                cache_service.cache_set(cache_key, result, ttl=MAP_TTL)
                return result
            logger.warning(f"驾车路线无结果(第{attempt + 1}次): {origin}→{dest} info={data.get('info')}")
        except Exception as e:
            logger.warning(f"驾车路线异常(第{attempt + 1}次): {origin}→{dest} {e}")
        if attempt == 0:
            time.sleep(0.6)  # 短暂等待后重试
    return None


# ---------- 4. 行程补全：给 Activity 加真实地理信息 ----------
def enrich_activity(activity: dict, city: str) -> dict:
    """把行程里的一个景点补全：POI ID、坐标、地址、图片。

    原理：先用景点名在高德搜 POI（city 限定城市，避免跨城污染），
    取第一个结果补全；找不到则保留原样（不阻塞行程）。
    """
    name = activity.get("place", "")
    if not name:
        return activity

    pois = search_poi(name, city, limit=1)
    if not pois:
        return activity
    poi = pois[0]
    activity["poi_id"] = poi["poi_id"]
    activity["address"] = poi["address"] or poi["formatted_address"]
    activity["image_url"] = poi["image_url"]
    activity["open_time"] = poi.get("open_time", "")  # 营业时间（真实值）
    activity["rating"] = poi.get("rating", "")        # 高德评分（真实值）
    if not activity.get("location"):
        activity["location"] = poi["location"]
    if not activity.get("location"):
        # POI 坐标偶发为空：用地址地理编码兜底（保证路线可算）
        geo = geocode(poi.get("address") or name, city)
        if geo and "," in geo.get("location", ""):
            activity["location"] = geo["location"]
    activity["lng"] = poi["lng"]
    activity["lat"] = poi["lat"]
    return activity


def enrich_itinerary(itinerary: dict, city: str) -> dict:
    """整份行程补全：每个活动补 POI 信息（坐标/地址/图片）。

    说明：不再计算相邻景点车程——用户出发起点不确定，
    车程没有实际参考价值，且能减少一半高德请求（避免 QPS 限流）。
    """
    for day in itinerary.get("days", []):
        for slot in ("morning", "afternoon", "evening"):
            acts = day.get(slot, [])
            for a in acts:
                a = enrich_activity(a, city)
    return itinerary
