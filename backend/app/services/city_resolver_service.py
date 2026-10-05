# ============================================
# 城市解析服务（city_resolver_service）
# 职责：把用户输入的目的地解析成"覆盖等级"，决定走哪条生成路径
# 分级：
#   A 级：沉淀城市（有本地攻略）→ RAG 攻略增强
#   B 级：动态城市（真实存在但无攻略）→ 高德 POI 候选池 + POI ID 白名单
#   C 级：资料不足（高德也查不到）→ LLM 通用知识兜底（并如实告知）
#   D 级：省级/直辖市级输入 → 不规划（提示选具体城市）
# 原理：先本地注册表，再查高德行政区划（district）验证"城市确实存在"
# ============================================
import logging
import re

import httpx

from app.config import settings
from app.services import city_registry_service

logger = logging.getLogger(__name__)


def resolve_city(raw: str) -> dict:
    """解析目的地 → {city, level, reason, adcode}。"""
    raw = _extract_city_name(raw or "")
    city = city_registry_service.normalize_city(raw)

    # 1. 省级/直辖市级输入（提取后仍是省名）→ D
    if city_registry_service.is_province_level(raw):
        return {"city": city, "level": "D", "reason": "省级输入，请选择具体城市", "adcode": ""}

    # 2. 沉淀城市（有攻略）→ A
    if city_registry_service.is_settled(city):
        return {"city": city, "level": "A", "reason": "本地攻略覆盖", "adcode": ""}

    # 3. 高德行政区划验证城市是否存在 → B / C
    adcode, found = _amap_district(city)
    if found:
        return {"city": city, "level": "B", "reason": "动态城市（高德验证存在）", "adcode": adcode}
    return {"city": city, "level": "C", "reason": "资料不足（未查到行政区）", "adcode": ""}


def _extract_city_name(raw: str) -> str:
    """提取城市名：'四川省成都市'→'成都市'、'大理白族自治州'→'大理白族自治州'。

    原理：输入带'省/自治区'时，末尾的'XX市/XX州/XX地区/XX盟'才是具体城市。
    """
    if "省" in raw or "自治区" in raw:
        m = re.search(r"([^省]+?(?:市|州|地区|盟))$", raw)
        if m:
            return m.group(1)
    return raw


def _amap_district(city: str) -> tuple[str, bool]:
    """高德行政区划查询：keywords=城市名 → (adcode, 是否存在)。

    district 接口返回的 districts[0] 若存在且是区县级以上，视为城市真实存在。
    """
    try:
        resp = httpx.get(
            f"{settings.AMAP_BASE_URL}/config/district",
            params={"keywords": city, "subdistrict": 0, "key": settings.AMAP_WEB_KEY},
            timeout=15,
        )
        data = resp.json()
        districts = data.get("districts") or []
        if not districts:
            return "", False
        d = districts[0]
        level = d.get("level", "")
        # level ∈ {country, province, city, district}；城市规划至少 city 级
        # （直辖市如"重庆"是 province 级，但已在攻略 A 级处理）
        if level in ("city", "province"):
            return d.get("adcode", ""), True
        return d.get("adcode", ""), False
    except Exception as e:
        logger.warning(f"高德行政区查询失败 {city}: {e}")
        return "", False
