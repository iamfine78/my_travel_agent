# ============================================
# Pydantic 请求/响应模型（接口层的数据"合同"）
# 作用：定义 API 收什么、返回什么，自动做参数校验和文档生成
# 原理：Pydantic 声明一个类 → FastAPI 自动：
#       1) 校验请求体是否符合字段类型（不合法直接 422 报错）
#       2) 把 Python 对象序列化成 JSON 响应
# ============================================
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------- 请求模型 ----------
class TripPlanRequest(BaseModel):
    """用户发起一次行程规划的请求体。"""

    destination: str = Field(..., description="目的地，如：西安", min_length=1)
    days: int = Field(3, ge=1, le=30, description="旅行天数 1~30")
    budget: float = Field(2000.0, gt=0, description="总预算（元）")
    companions: str = Field("独自", description="同行人：独自/情侣/亲子/家庭/朋友")
    preferences: str = Field("", description="偏好描述，如：喜欢人文景点、爱吃辣")
    # 多模态：用户上传的图片（base64 字符串，可空）。后端转给 deepseek-flash 识别
    image_base64: Optional[str] = Field(None, description="用户上传图片的 base64 内容")


class TripEditRequest(BaseModel):
    """用自然语言修改某一天行程的请求体。"""

    instruction: str = Field(..., description="编辑指令，如：第二天换成轻松一点的行程")


class TripSummaryIn(BaseModel):
    """保存行程的请求体（前端把结果页内容发回来保存）。"""

    destination: str = Field(..., min_length=1)
    summary: str = ""
    itinerary_json: dict = Field(default_factory=dict, description="完整行程的字典")


# ---------- 行程结构化模型（LLM 输出的"合同"） ----------
class Activity(BaseModel):
    """一天的某个时段里的一个活动/景点。"""

    place: str = Field(..., description="地点名称")
    description: str = Field("", description="活动说明")
    play_guide: str = Field("", description="到景点后怎么玩：推荐游玩时长、必看亮点、注意事项")
    poi_id: str = Field("", description="高德 POI ID（B级动态城市必填，防幻觉）")
    address: str = Field("", description="地址（高德补全）")
    image_url: str = Field("", description="景点图片（高德补全）")
    open_time: str = Field("", description="营业时间（高德补全，如 09:00-22:00）")
    # cost 放宽为数字或文本：LLM 经常输出"成人120元，儿童免费"这类描述
    # （预算汇总用 budget_split 里的数字，这里的 cost 主要给前端展示）
    cost: float | str = Field(0, description="预估花费（元）或价格描述")


class ItineraryDay(BaseModel):
    """一天的三段式行程。"""

    day: int = Field(..., ge=1, description="第几天")
    date_hint: str = Field("", description="日期提示，如：10月8日 周三")
    morning: list[Activity] = Field(default_factory=list)
    afternoon: list[Activity] = Field(default_factory=list)
    evening: list[Activity] = Field(default_factory=list)
    meals: list[str] = Field(default_factory=list, description="餐饮建议")
    lodging: str = Field("", description="当天住宿安排：建议住哪个区域/酒店类型及理由")
    note: str = Field("", description="当日小贴士")


class Itinerary(BaseModel):
    """完整行程：多天 + 预算拆分 + 摘要。"""

    destination: str
    days: list[ItineraryDay]
    budget_split: dict = Field(
        default_factory=dict, description="交通/住宿/餐饮/门票/其他 分项预算"
    )
    summary: str = Field("", description="行程一句话摘要")
    tips: list[str] = Field(default_factory=list, description="整体建议")


# ---------- 响应模型 ----------
class TripRecordOut(BaseModel):
    """历史行程的返回结构（一条）。"""

    trip_id: str
    destination: str
    summary: str
    itinerary: dict = Field(default_factory=dict, description="解析后的行程 JSON")
    created_at: datetime
    updated_at: datetime


class TripListOut(BaseModel):
    """历史列表：records 是 TripRecordOut 的数组。"""

    total: int
    records: list[TripRecordOut]


class PlanResponse(BaseModel):
    """行程规划接口的返回：结构化行程 + 附加信息。"""

    trip_id: str
    destination: str
    itinerary: dict = Field(default_factory=dict)   # 按天分组的完整行程
    budget_split: dict = Field(default_factory=dict)  # 交通/住宿/餐饮/门票/其他
    weather: Optional[dict] = None                    # 逐日天气预报
    sources: list[str] = Field(default_factory=list)  # 信息引用来源（攻略/高德）
    token_usage: dict = Field(default_factory=dict)   # 本次请求分项 token 消耗（rewrite/rerank/planner）
