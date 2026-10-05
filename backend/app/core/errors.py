# ============================================
# 业务异常体系
# 职责：给"业务上可预期的失败"一个明确的类型 + HTTP 状态，
#       由 api/main.py 统一注册的 handler 转成响应。
# 原理：
#   - 各层只管抛语义清晰的异常，不必知道 HTTP 状态码；
#   - status_code 作为类属性写在异常上，路由与 service 都不重复映射；
#   - 未继承 PlanningError 的异常仍走 FastAPI 默认的 500，不会被吞掉。
# 与 HTTPException 的分工：HTTPException 用于"接口层自己发现的问题"
#   （如路径参数指向的记录不存在），本模块用于"业务层抛出的问题"。
# ============================================


class PlanningError(Exception):
    """业务异常基类：可预期的失败，映射为 400。"""

    status_code: int = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnsupportedDestinationError(PlanningError):
    """目的地无法用于规划：省级输入、查不到的城市等（D 级 / 资料不足）。"""

    status_code = 400


class TripNotFoundError(PlanningError):
    """指定的行程不存在（或已被删除）。"""

    status_code = 404


class ItineraryGenerationError(PlanningError):
    """LLM 多次输出仍无法解析成合法行程 —— 上游能力故障，不是用户的错。"""

    status_code = 502


class UpstreamServiceError(PlanningError):
    """依赖的外部服务（高德等）暂时不可用 —— 不是用户输入的问题，可稍后重试。"""

    status_code = 502
