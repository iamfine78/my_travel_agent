# ============================================
# FastAPI 应用入口
# 作用：创建应用实例、挂 CORS、注册路由、提供健康检查
# 原理：
#   - FastAPI() 创建应用；include_router 把各路由文件"挂"到应用上
#   - CORS 中间件：允许前端 Vue（5173 端口）跨域调用本后端
#   - lifespan 钩子：应用启动时自动建数据库表
# ============================================
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 2.x 推荐的启动/关闭钩子。启动时建表。"""
    storage_service.init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# 跨域配置（开发阶段放开，生产环境收紧到前端域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由：trip（生成/编辑/历史）、export（导出）、weather（天气）
from app.api.routes import export, trip, weather  # noqa: E402

app.include_router(trip.router, prefix="/api/trip", tags=["行程"])
app.include_router(export.router, prefix="/api/export", tags=["导出"])
app.include_router(weather.router, prefix="/api/weather", tags=["天气"])


@app.get("/api/health")
def health():
    """健康检查：前端和部署脚本用这个确认后端活着。"""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
