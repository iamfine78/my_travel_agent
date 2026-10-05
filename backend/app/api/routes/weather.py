# ============================================
# 天气路由：天气预报接口
# 作用：前端按城市查天气（高德天气 + Redis 缓存）
# ============================================
from fastapi import APIRouter, HTTPException

from app.services import weather_service

router = APIRouter()


@router.get("/{city}", summary="查询城市天气预报")
def get_weather(city: str):
    """返回 3 天预报 + 实时天气。城市不存在返回 404。"""
    result = weather_service.get_weather(city)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到城市天气: {city}")
    return result
