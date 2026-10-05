# ============================================
# 行程路由：生成 / 编辑 / 历史 CRUD
# 作用：接口层的"接待员"——收请求、校验参数、调服务层、返回结果
# 原理：FastAPI 路由装饰器 + Pydantic 模型自动校验。
#       M1 阶段：历史 CRUD 已可用；plan 与 edit 在 M2 接 LLM 后实现。
# ============================================
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    PlanResponse,
    TripEditRequest,
    TripListOut,
    TripPlanRequest,
    TripRecordOut,
)
from app.services import storage_service

router = APIRouter()


@router.post("/plan", response_model=PlanResponse, summary="生成旅行规划")
def plan_trip(req: TripPlanRequest):
    """调用 LLM（+RAG/高德候选池）生成结构化行程。

    业务失败（如省级输入）由 trip_service 抛 PlanningError，
    在 api/main.py 统一映射成 HTTP 响应，这里不必再 catch。
    """
    from app.services import trip_service

    return trip_service.plan_trip(req)


@router.post("/{trip_id}/edit", response_model=PlanResponse, summary="自然语言编辑行程")
def edit_trip(trip_id: str, req: TripEditRequest):
    """用一句话修改某天的行程。"""
    from app.services import trip_service

    return trip_service.edit_trip(trip_id, req)


@router.post("/{trip_id}/refresh", response_model=TripRecordOut, summary="补全旧行程的地理信息")
def refresh_trip(trip_id: str):
    """旧版本生成的行程缺车程/坐标：重新调用高德补全并保存。

    原理：读历史存储 → 重新 enrich（POI 坐标 + 相邻车程）→ 写回数据库。
    """
    from app.services import map_service

    record = storage_service.get_trip(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="行程不存在")

    itinerary = storage_service.to_record_out(record)["itinerary"]
    enriched = map_service.enrich_itinerary(itinerary, record.destination)
    updated = storage_service.update_trip(trip_id, enriched)
    return storage_service.to_record_out(updated)


# ---------- 历史管理（M1 已可用） ----------
@router.post("", response_model=TripRecordOut, status_code=201, summary="保存行程")
def save_trip(payload: dict):
    """前端把生成好的行程发回来持久化。token_usage 一并存进行程 JSON 长期保留。"""
    itinerary = payload.get("itinerary_json", {})
    # Token 观测：把本次生成的 token 消耗随行程保存（stats 汇总用）
    if payload.get("token_usage"):
        itinerary["_token_usage"] = payload["token_usage"]
    record = storage_service.create_trip(
        destination=payload.get("destination", ""),
        summary=payload.get("summary", ""),
        itinerary=itinerary,
    )
    return storage_service.to_record_out(record)


@router.get("/history", response_model=TripListOut, summary="历史行程列表")
def trip_history(limit: int = 20, offset: int = 0):
    records = storage_service.list_trips(limit=limit, offset=offset)
    return {
        # total 用真实总数：以前用 len(records)，分页时它恒等于当页条数，
        # 前端算不出总页数
        "total": storage_service.count_trips(),
        "records": [storage_service.to_record_out(r) for r in records],
    }


@router.get("/stats", summary="Token 观测汇总")
def trip_stats():
    """汇总 token 消耗：session=当前进程累计（含未保存），saved=已保存行程累计。"""
    from app.services.token_tracker import PHASES, token_tracker

    # 已保存行程的 token：从每条行程的 itinerary_json["_token_usage"] 聚合
    import json

    saved = {p: {"prompt": 0, "completion": 0, "total": 0} for p in PHASES}
    saved_req = {p: 0 for p in PHASES}
    for rec in storage_service.list_trips(limit=1000):
        try:
            itin = json.loads(rec.itinerary_json or "{}")
        except Exception:
            itin = {}
        usage = itin.get("_token_usage") or {}
        for p in PHASES:
            d = usage.get(p) or {}
            saved[p]["prompt"] += int(d.get("prompt", 0) or 0)
            saved[p]["completion"] += int(d.get("completion", 0) or 0)
            saved[p]["total"] += int(d.get("total", 0) or 0)
            if d.get("total"):
                saved_req[p] += 1

    session = token_tracker.snapshot()
    return {
        "session": session,
        "saved": {
            "by_phase": saved,
            "requests": saved_req,
            "total": sum(saved[p]["total"] for p in PHASES),
        },
    }


@router.get("/{trip_id}", response_model=TripRecordOut, summary="行程详情")
def trip_detail(trip_id: str):
    record = storage_service.get_trip(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    return storage_service.to_record_out(record)


@router.delete("/{trip_id}", status_code=204, summary="删除行程")
def trip_delete(trip_id: str):
    ok = storage_service.delete_trip(trip_id)
    if not ok:
        raise HTTPException(status_code=404, detail="行程不存在")
