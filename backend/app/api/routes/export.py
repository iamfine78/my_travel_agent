# ============================================
# 导出路由：Markdown / 中文 PDF
# 两种方式：
#   POST /api/export/{trip_id}?format=md|pdf   → 从历史行程导出
#   POST /api/export/from-data?format=md|pdf   → 用前端当前页面数据导出（body 传 itinerary）
# ============================================
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from app.services import export_service, storage_service

router = APIRouter()


@router.post("/from-data", summary="用当前页面数据导出 Markdown / PDF")
def export_current(payload: dict, format: str = Query("md", pattern="^(md|pdf)$")):
    """前端结果页把当前 itinerary 发来，导出即所见即所得。

    注意：必须定义在 /{trip_id} 之前，否则 "from-data" 会被当作 trip_id 匹配。
    """
    itinerary = payload.get("itinerary") or payload.get("itinerary_json") or {}
    destination = payload.get("destination") or itinerary.get("destination") or "旅行"
    weather = payload.get("weather") or itinerary.get("weather_data")
    return _build_response(itinerary, destination, format, weather)


@router.post("/{trip_id}", summary="从历史行程导出 Markdown / PDF")
def export_trip(trip_id: str, format: str = Query("md", pattern="^(md|pdf)$")):
    record = storage_service.get_trip(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    itinerary = storage_service.to_record_out(record)["itinerary"]
    weather = itinerary.get("weather_data")
    return _build_response(itinerary, record.destination, format, weather)


def _build_response(itinerary: dict, destination: str, format: str, weather: dict | None = None):
    """按格式生成响应（md 返回文本，pdf 返回文件流）。"""
    if format == "md":
        md = export_service.itinerary_to_markdown(itinerary, destination, weather)
        return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")
    else:
        try:
            pdf_bytes = export_service.itinerary_to_pdf_bytes(itinerary, destination, weather)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        # Content-Disposition 文件名必须 ASCII（HTTP header 仅支持 latin-1），
        # 中文目的地名会导致编码崩溃 → 用固定英文文件名
        filename = "travel_itinerary.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
