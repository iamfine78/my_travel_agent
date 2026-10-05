# ============================================
# 旅行规划 Agent（核心：LLM 生成结构化行程）
# 职责：调用 deepseek-flash 生成结构化旅行草稿；
#       支持多模态（用户上传图片 → 识别后纳入规划）；
#       单日编辑（自然语言改某天行程）
# 原理：
#   - LangChain 的 ChatOpenAI 以 OpenAI 兼容协议连 deepseek
#   - 提示词要求输出"严格 JSON"，配合 response_format=json_object，
#     再用 Pydantic(Itinerary) 校验——LLM 自由发挥 + 程序强约束
#   - 多模态：HumanMessage 里同时放文本和 image_url（base64），
#     deepseek-flash 原生支持看图
# ============================================
import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.errors import ItineraryGenerationError
from app.models.schemas import Itinerary, TripEditRequest, TripPlanRequest

logger = logging.getLogger(__name__)

# 生成行程的系统提示词：约束输出 JSON 结构与规范
PLAN_SYSTEM_PROMPT = """你是一位资深的旅行规划专家。根据用户需求生成结构化旅行规划。
必须遵守以下规则：
1. 输出必须是合法 JSON，不要包含 markdown 代码块标记，不要有任何额外文字。
2. JSON 结构必须严格符合:
{{
  "destination": "目的地",
  "summary": "一句话行程摘要",
  "days": [
    {{
      "day": 1,
      "date_hint": "第X天",
      "morning": [{{"place": "景点名", "description": "简要说明", "play_guide": "到景点后怎么玩", "cost": 预估花费}}],
      "afternoon": [...],
      "evening": [...],
      "meals": ["餐饮建议"],
      "lodging": "当天住宿安排",
      "note": "当日提示"
    }}
  ],
  "budget_split": {{"transport": 交通预算, "lodging": 住宿, "food": 餐饮, "tickets": 门票, "other": 其他}},
  "tips": ["整体建议"]
}}
3. 每天必须包含 morning / afternoon / evening 三个时段，每个时段至少 1 个活动。
4. 预算拆分 5 项之和应约等于用户总预算。
5. 景点必须真实存在，优先推荐知名、评价好的地点。
6. 每个活动的 play_guide 字段要写"到达该景点后具体怎么玩"：推荐游玩时长、必看亮点、注意事项，30~60 字。
7. 每天必须写 lodging 字段：建议当晚住在哪个区域（或哪种酒店类型）及理由，结合当天行程动线安排。
8. 用中文回答。
"""

EDIT_SYSTEM_PROMPT = """你是一位资深旅行规划专家。用户会用一句话要求修改现有行程中的某一天。
请重新输出修改后的完整行程 JSON，结构规则与生成时完全一致。
只调整用户要求的部分，其他天的安排保持不变。
"""

# B 级动态城市提示词：只允许输出候选池内的 POI ID（防幻觉）
# 与 PLAN_SYSTEM_PROMPT 的区别：place 必须带 poi_id，且 poi_id 必须在候选池内
DYNAMIC_PLAN_SYSTEM_PROMPT = """你是一位资深的旅行规划专家。根据用户需求生成结构化旅行规划。
必须遵守以下规则：
1. 输出必须是合法 JSON，不要包含 markdown 代码块标记，不要有任何额外文字。
2. JSON 结构必须严格符合:
{{
  "destination": "目的地",
  "summary": "一句话行程摘要",
  "days": [
    {{
      "day": 1,
      "date_hint": "第X天",
      "morning": [{{"place": "景点名", "poi_id": "候选池中的POI_ID", "description": "简要说明", "play_guide": "到景点后怎么玩", "cost": 预估花费}}],
      "afternoon": [...],
      "evening": [...],
      "meals": ["餐饮建议"],
      "lodging": "当天住宿安排",
      "note": "当日提示"
    }}
  ],
  "budget_split": {{"transport": 交通预算, "lodging": 住宿, "food": 餐饮, "tickets": 门票, "other": 其他}},
  "tips": ["整体建议"]
}}
3. 每天必须包含 morning / afternoon / evening 三个时段，每个时段至少 1 个活动。
4. 预算拆分 5 项之和应约等于用户总预算。
5. 【最关键】每个 activity 的 place 和 poi_id 必须来自消息中提供的【候选地点】列表；
   严禁输出候选列表之外的地点，严禁编造 POI_ID。
6. 餐饮（meals 之外的地点）与住宿安排也应优先从候选池选择。
7. 每个活动的 play_guide 字段要写"到达该景点后具体怎么玩"：推荐游玩时长、必看亮点、注意事项，30~60 字。
8. 每天必须写 lodging 字段：建议当晚住在哪个区域（或哪种酒店类型）及理由。
9. 用中文回答。
"""


class TripPlannerAgent:
    """封装 LLM 调用的 Agent。初学者视角：一个"会聊天的行程大脑"。"""

    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL_ID,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT,
            temperature=settings.LLM_TEMPERATURE,
            # 要求模型输出 JSON 对象（deepseek 支持 OpenAI 兼容的 json_object 模式）
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    # ---------- 生成行程 ----------
    def plan_trip(self, req: TripPlanRequest, extra_context: str = "", mode: str = "settled") -> dict:
        """生成结构化行程。

        mode: "settled"=攻略城市(RAG 增强) / "dynamic"=动态城市(POI ID 白名单) /
              "fallback"=资料不足(LLM 通用知识)
        """
        user_text = self._build_user_text(req, extra_context)
        system_prompt = DYNAMIC_PLAN_SYSTEM_PROMPT if mode == "dynamic" else PLAN_SYSTEM_PROMPT

        # 多模态：用户上传了图片 → 文本消息 + 图片消息一起发给模型
        messages = [SystemMessage(content=system_prompt)]
        if req.image_base64:
            messages.append(
                HumanMessage(
                    content=[
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            # base64 图片按 data URI 传（JPEG/PNG 均可，deepseek 原生支持）
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{req.image_base64}"
                            },
                        },
                    ]
                )
            )
        else:
            messages.append(HumanMessage(content=user_text))

        # 调用模型；解析失败自动重试一次（LLM 偶发格式问题很常见）
        return self._parse_json_safely(messages, phase="planner")

    # ---------- 单日编辑 ----------
    def edit_trip(self, current_itinerary: dict, req: TripEditRequest) -> dict:
        """用一句自然语言修改行程，返回全新完整行程。"""
        current_json = json.dumps(current_itinerary, ensure_ascii=False)
        user_text = f"当前行程：\n{current_json}\n\n修改指令：{req.instruction}"
        messages = [
            SystemMessage(content=EDIT_SYSTEM_PROMPT),
            HumanMessage(content=user_text),
        ]
        return self._parse_json_safely(messages, phase="edit")

    # ---------- 内部工具 ----------
    def _build_user_text(self, req: TripPlanRequest, extra_context: str) -> str:
        """把用户需求拼成一段清晰的文本请求。"""
        text = (
            f"请为「{req.destination}」规划 {req.days} 天旅行。\n"
            f"同行人：{req.companions}\n"
            f"总预算：{req.budget} 元\n"
            f"偏好：{req.preferences or '无特别偏好'}\n"
        )
        if req.image_base64:
            text += "附上了一张图片，请先识别图片内容（景点/场景/风格），若与旅行相关则纳入规划考虑。\n"
        if extra_context:
            text += f"\n【参考资料】\n{extra_context}\n"
        return text

    def _parse_json_safely(self, messages, phase: str = "planner") -> dict:
        """调用 LLM 并解析 JSON；失败重试一次，再失败抛异常。"""
        from app.services.token_tracker import token_tracker

        for attempt in range(2):
            try:
                resp = self.llm.invoke(messages)
                token_tracker.record(phase, resp.response_metadata)  # Token 观测
                data = json.loads(resp.content)
                # Pydantic 校验结构是否合规（缺字段会抛 ValidationError）
                Itinerary(**data)
                return data
            except Exception as e:
                logger.warning(f"LLM 输出解析失败（第{attempt+1}次）: {e}")
        raise ItineraryGenerationError("LLM 多次输出无效 JSON，请重试")


# 模块级单例：全项目共用一个 agent（避免重复建连接）
planner_agent = TripPlannerAgent()
