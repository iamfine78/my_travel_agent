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
import time
from typing import NamedTuple

import httpx

from app.config import settings
from app.services import city_registry_service

logger = logging.getLogger(__name__)

# "输入城市名 → 高德返回的区划名"匹配时允许的后缀。
# 刻意不含「区」「县」：它们是下级区划而非城市，若纳入则
# 「西安」会匹配上吉林的「西安区」，把区县当成城市（这正是要修的坑）。
# 县级市叫「XX市」，由「市」覆盖。
_ADMIN_SUFFIXES = ("市", "州", "地区", "盟")

# 查询失败时的重试间隔（秒）：高德偶发抖动重试一次能挡掉大部分误判
_DISTRICT_RETRY_WAIT = 0.6


class DistrictResult(NamedTuple):
    """行政区划查询结果。

    failed 与 found=False 是两回事：
      - found=True              → 城市真实存在
      - found=False,failed=False → 确实查不到（如生僻地名）
      - found=False,failed=True  → 高德调用失败/超时，**不能据此断定城市不存在**
    区分开是为了不把"网络抖了一下"静默说成"这城市查不到"。
    """

    adcode: str
    found: bool
    failed: bool = False


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
    result = _amap_district(city)
    if result.found:
        return {"city": city, "level": "B", "reason": "动态城市（高德验证存在）", "adcode": result.adcode}
    if result.failed:
        # 高德不可用不等于"该城市不存在"，如实说明，避免把故障说成资料不足
        return {"city": city, "level": "C", "reason": "高德查询失败，暂用通用知识生成", "adcode": ""}
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


def _amap_district(city: str) -> DistrictResult:
    """高德行政区划查询：keywords=城市名 → 代表该城市的那条区划。

    两个坑都在这里兜住：
      1) 不能盲取 districts[0]。高德对同一关键词会返回多条同名区县——
         「西安」会返回吉林辽源与黑龙江的「西安区」，真正的「西安市」排在后面。
         盲取第一条会把西安判成"不存在"。
      2) 调用失败要能和"确实查不到"区分开，失败时重试一次。
    """
    data = _district_request(city)
    if data is None:
        return DistrictResult("", False, failed=True)
    picked = _pick_city_district(data.get("districts") or [], city)
    if picked is None:
        return DistrictResult("", False)
    return DistrictResult(picked.get("adcode", ""), True)


def _district_request(city: str) -> dict | None:
    """带一次重试的行政区划请求。返回 None 表示「调用失败」。

    关键：高德用 **HTTP 200 + status="0"** 表达配额超限、鉴权失败等业务错误，
    所以不能只看 HTTP 状态码——必须检查业务状态位。否则限流会被误读成
    「这个城市查不到」（实测：连续查询时丽江/咸阳/阿坝会被判成 C 级）。
    """
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = httpx.get(
                f"{settings.AMAP_BASE_URL}/config/district",
                params={"keywords": city, "subdistrict": 0, "key": settings.AMAP_WEB_KEY},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "1":
                raise RuntimeError(
                    f"高德业务错误 status={data.get('status')!r} info={data.get('info')!r}"
                )
            return data
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(_DISTRICT_RETRY_WAIT)
    logger.warning(f"高德行政区查询失败（已重试一次）city={city}: {last_err}")
    return None


def _bare_admin_name(name: str) -> str:
    """去掉行政后缀：「大理白族自治州」→「大理白族自治」。"""
    return re.sub(r"[市州地区盟县区]$", "", str(name or ""))


def _pick_city_district(districts: list[dict], city: str) -> dict | None:
    """从候选里挑出真正代表输入城市的那条区划。

    按"具体到宽泛"的顺序，避免选到州级或同名区县：
      1) 名称 == 输入 + 城市级后缀 →「大理」取到「大理市」(532901) 而非「大理白族自治州」(532900)
      2) 名称去后缀后相同，且必须是 city/province 级 → 容错输入本身带后缀
      3) 任意 city/province 级条目 → 没有同名市时退回州级（如「阿坝」→「阿坝藏族羌族自治州」）
    区县级条目一律不选：区县不是可规划的城市。
    """
    if not districts:
        return None

    for suffix in _ADMIN_SUFFIXES:
        for d in districts:
            if str(d.get("name", "")) == f"{city}{suffix}":
                return d

    target = _bare_admin_name(city)
    for d in districts:
        if d.get("level") in ("city", "province") and _bare_admin_name(d.get("name", "")) == target:
            return d

    for d in districts:
        if d.get("level") in ("city", "province"):
            return d
    return None
