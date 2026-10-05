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
from app.core.errors import TripNotFoundError, UnsupportedDestinationError
from app.models.schemas import BudgetBreakdown, PlanResponse, TripEditRequest, TripPlanRequest
from app.rag import retriever
from app.services import (
    city_resolver_service,
    fallback_candidates,
    map_service,
    place_candidate_service,
    weather_service,
)

logger = logging.getLogger(__name__)

# 和值偏差在 ±5% 内视为合理：LLM 估算本就不精确，不值得为此改动用户的数
BUDGET_TOLERANCE = 0.05


def normalize_budget(raw: dict | None, total: float) -> dict:
    """把预算拆分校准成「五项之和 ≈ 用户总预算」的确定值。

    为什么需要：LLM 给的五项之和经常与用户填的总预算对不上（漏项、凑数），
    直接展示会让用户以为系统算错了。这里做一次确定性校准：
      和值为 0 或总预算非正 → 原样返回；偏差在容差内 → 只四舍五入；
      超出容差 → 按比例整体缩放，且和值精确等于总预算。
    """
    breakdown = BudgetBreakdown.from_raw(raw)
    current = breakdown.total
    if current <= 0 or not total or total <= 0:
        return breakdown.as_dict()
    if abs(current - total) / total <= BUDGET_TOLERANCE:
        return breakdown.as_dict()
    return breakdown.scaled_to(total)


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
        raise UnsupportedDestinationError(f"{reason}：请选择具体城市（如：大理、西安、成都）")

    # 2. 按等级准备生成上下文（攻略片段 / 候选池 / 空）
    context, sources = extra_context, []
    mode = "settled"
    pool: dict = {}   # 仅 B 级会填充；第 4 步用它做池外校验
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
        try:
            pool = place_candidate_service.get_candidates(city, resolved.get("adcode", ""))
        except Exception as e:
            # 候选池拿不到 → POI ID 白名单约束不复存在，降级为通用知识生成并如实标注
            # （mode 同时用作第 4 步的开关：非 dynamic 时不做池外校验，否则会把行程清空）
            mode = "fallback"
            pool = {}
            sources = [f"{city}高德候选池获取失败，改用通用知识生成（地点未校验）"]
            logger.warning(f"B 级候选池获取失败，降级为通用知识: {e}")
        else:
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
    #    仅在候选池真的拿到了才校验：池子为空时校验会把行程清空
    if level == "B" and mode == "dynamic":
        itinerary, stats = _validate_pool(itinerary, pool)
        if stats["replaced"] or stats["removed"]:
            sources.append(f"候选校验：替换 {stats['replaced']} 个、移除 {stats['removed']} 个池外地点")

    # 5. 高德补全（坐标/地址/图片）+ 天气
    #    这两步是"锦上添花"：外部服务失败时保留 LLM 原始输出即可，
    #    不该让整个规划请求 500（与 Redis / 精排的降级策略保持一致）
    try:
        itinerary = map_service.enrich_itinerary(itinerary, city)
    except Exception as e:
        sources.append("高德地理信息补全失败，坐标/图片可能缺失")
        logger.warning(f"高德补全失败，跳过: {e}")

    weather = None
    try:
        weather = weather_service.get_weather(city)
    except Exception as e:
        sources.append("天气获取失败")
        logger.warning(f"天气获取失败，跳过: {e}")

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

    # 6. 预算校准：LLM 给的五项之和常与用户总预算对不上，按比例校准后再返回
    budget_split = normalize_budget(itinerary.get("budget_split"), req.budget)
    itinerary["budget_split"] = budget_split

    # 7. 组装响应（含本次请求的 token 分项统计）
    token_usage = token_tracker.diff(before, token_tracker.snapshot())
    # Token 观测：终端同步打印本次消耗
    logger.info(f"Token 本次请求: { {p: d['total'] for p, d in token_usage.items() if d['total']} }")
    return PlanResponse(
        trip_id=uuid.uuid4().hex,
        destination=city,
        itinerary=itinerary,
        budget_split=budget_split,
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
    """根据用户一句话修改行程：读已保存行程 → 编辑 → 补全 → 回写。"""
    from app.services import storage_service

    record = storage_service.get_trip(trip_id)
    if record is None:
        raise TripNotFoundError("行程不存在")

    current = storage_service.to_record_out(record)["itinerary"]
    destination = current.get("destination", record.destination)
    new_itinerary = planner_agent.edit_trip(current, req)

    # 编辑可能引入新地点：补全坐标/地址/图片，否则前端地图会丢标记。
    # 高德偶发失败不应让编辑整个失败，故降级为「保留原样」。
    try:
        new_itinerary = map_service.enrich_itinerary(new_itinerary, destination)
    except Exception as e:
        logger.warning(f"编辑后补全地图信息失败，跳过: {e}")

    # 回写存储：不回写的话用户看到改了、历史里还是旧的
    storage_service.update_trip(trip_id, new_itinerary)

    return PlanResponse(
        trip_id=trip_id,
        destination=destination,
        itinerary=new_itinerary,
        budget_split=new_itinerary.get("budget_split", {}),
        sources=[],
    )
