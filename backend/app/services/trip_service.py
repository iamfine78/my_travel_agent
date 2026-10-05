# ============================================
# 行程主编排服务
# 职责：A/B/C/D 四级城市分流的主流程编排
#   A 级（有攻略）   ：Query Rewrite → RAG 检索 → 攻略增强生成
#   B 级（动态城市） ：高德候选池 → POI ID 白名单生成 → 池外 ID 校验拒绝
#   C 级（资料不足） ：LLM 通用知识兜底（如实标注来源）
#   D 级（省级输入） ：拒绝，提示选具体城市
# 原理：接口层只负责收发，真正的业务"串流程"在这里
# ============================================
import logging
import uuid

from app.agents.trip_planner_agent import planner_agent
from app.agents.tools import rag_tool
from app.models.schemas import PlanResponse, TripEditRequest, TripPlanRequest
from app.rag import retriever
from app.services import (
    city_resolver_service,
    fallback_candidates,
    map_service,
    place_candidate_service,
    weather_service,
)

logger = logging.getLogger(__name__)


def plan_trip(req: TripPlanRequest, extra_context: str = "") -> PlanResponse:
    """生成行程的主入口。四级分流：A 攻略 / B 动态候选池 / C 通用 / D 拒绝。"""
    from app.services.token_tracker import token_tracker

    # Token 观测：记录本次请求前的累计快照（用于算增量）
    before = token_tracker.snapshot()

    # 1. 城市分级（本地注册表 → 高德行政区验证）
    resolved = city_resolver_service.resolve_city(req.destination)
    city, level, reason = resolved["city"], resolved["level"], resolved["reason"]
    req.destination = city

    if level == "D":
        raise ValueError(f"{reason}：请选择具体城市（如：大理、西安、成都）")

    # 2. 按等级准备生成上下文（攻略片段 / 候选池 / 空）
    context, sources = extra_context, []
    mode = "settled"
    if level == "A":
        mode = "settled"
        user_query = f"{city} 旅行 {req.preferences} {req.days}天"
        rewritten = rag_tool.rewrite_query(user_query, city=city)
        hits = retriever.retrieve_and_rerank(rewritten["query"], city=city)
        if hits:
            context = retriever.format_context(hits)
            sources = [f"{city}本地攻略（检索 {len(hits)} 条）"]
        else:
            # RAG 空召回 fallback：从攻略原文提取真实候选，防止 LLM 编造
            names = fallback_candidates.extract_from_guide(city)
            context = fallback_candidates.format_guide_candidates(names, city)
            sources = [f"{city}本地攻略（候选提取 {len(names)} 个）"]
        logger.info(f"A 级 RAG：city={city} 召回 {len(hits)} 条")
    elif level == "B":
        mode = "dynamic"
        pool = place_candidate_service.get_candidates(city)
        context = place_candidate_service.format_candidates(pool)
        total = sum(len(v) for v in pool.values())
        sources = [f"{city}高德候选池（{total} 个真实地点）"]
        logger.info(f"B 级动态：city={city} 候选池 {total} 个")
    else:  # C 级：资料不足
        mode = "fallback"
        sources = [f"{city}（{reason}，使用通用知识生成）"]
        logger.info(f"C 级兜底：city={city}")

    # 3. 调 LLM 生成（dynamic 模式强制 POI ID 白名单）
    itinerary = planner_agent.plan_trip(req, extra_context=context, mode=mode)

    # 4. B 级：池外 ID 校验拒绝（防幻觉核心）
    if level == "B":
        itinerary, stats = _validate_pool(itinerary, pool)
        if stats["replaced"] or stats["removed"]:
            sources.append(f"候选校验：替换 {stats['replaced']} 个、移除 {stats['removed']} 个池外地点")

    # 5. 高德补全（坐标/地址/图片）+ 天气
    itinerary = map_service.enrich_itinerary(itinerary, city)
    weather = weather_service.get_weather(city)

    # 天气感知修正：把天气提示注入行程建议
    if weather and weather.get("forecasts"):
        tips = itinerary.setdefault("tips", [])
        for cast in weather["forecasts"][:3]:
            text = cast.get("dayweather", "")
            if "雨" in text:
                tips.append(f"{cast.get('date', '')} 预计{text}，建议携带雨具，适当调整户外行程")
            elif "雪" in text:
                tips.append(f"{cast.get('date', '')} 预计{text}，注意保暖与防滑")
            elif "晴" in text and int(cast.get("daytemp", 0) or 0) >= 30:
                tips.append(f"{cast.get('date', '')} 晴天高温，注意防晒补水")

    # 6. 组装响应（含本次请求的 token 分项统计）
    token_usage = token_tracker.diff(before, token_tracker.snapshot())
    # Token 观测：终端同步打印本次消耗
    logger.info(f"Token 本次请求: { {p: d['total'] for p, d in token_usage.items() if d['total']} }")
    return PlanResponse(
        trip_id=uuid.uuid4().hex,
        destination=city,
        itinerary=itinerary,
        budget_split=itinerary.get("budget_split", {}),
        weather=weather,
        sources=sources,
        token_usage=token_usage,
    )


def _validate_pool(itinerary: dict, pool: dict) -> tuple[dict, dict]:
    """动态城市防幻觉校验：每个活动必须命中候选池（POI ID 或名称）。

    - poi_id 在池内 → 保留
    - 名字在池内但没 ID → 用池内数据补 poi_id
    - 池外 → 用未使用的景点候选替换；无可用则移除
    """
    ids = {it["poi_id"] for key in pool for it in pool[key]}
    by_name = {it["name"]: it for key in pool for it in pool[key]}
    # 未使用的景点候选（优先用于替换景点类活动）
    used_ids = set()
    for day in itinerary.get("days", []):
        for slot in ("morning", "afternoon", "evening"):
            for a in day.get(slot, []):
                if a.get("poi_id"):
                    used_ids.add(a["poi_id"])
    spare = [it for it in pool.get("scenic", []) if it["poi_id"] not in used_ids]

    replaced = removed = 0
    for day in itinerary.get("days", []):
        for slot in ("morning", "afternoon", "evening"):
            kept: list[dict] = []
            for a in day.get(slot, []):
                pid = a.get("poi_id", "")
                pname = a.get("place", "")
                if pid in ids:
                    kept.append(a)
                elif pname in by_name:
                    info = by_name[pname]
                    a["poi_id"] = info["poi_id"]
                    a["address"] = info["address"] or a.get("address", "")
                    kept.append(a)
                elif spare:
                    rep = spare.pop(0)
                    used_ids.add(rep["poi_id"])
                    a["place"] = rep["name"]
                    a["poi_id"] = rep["poi_id"]
                    a["address"] = rep["address"]
                    a["description"] = (a.get("description", "") + "（已按候选池调整）").strip()
                    replaced += 1
                    kept.append(a)
                else:
                    removed += 1  # 无候选可替 → 移除防幻觉
            day[slot] = kept
    return itinerary, {"replaced": replaced, "removed": removed}


def edit_trip(trip_id: str, req: TripEditRequest) -> PlanResponse:
    """根据用户一句话修改行程。从已保存行程读取再编辑。"""
    from app.services import storage_service

    record = storage_service.get_trip(trip_id)
    if record is None:
        raise ValueError("行程不存在")

    current = storage_service.to_record_out(record)["itinerary"]
    new_itinerary = planner_agent.edit_trip(current, req)

    return PlanResponse(
        trip_id=trip_id,
        destination=current.get("destination", record.destination),
        itinerary=new_itinerary,
        budget_split=new_itinerary.get("budget_split", {}),
        sources=[],
    )
