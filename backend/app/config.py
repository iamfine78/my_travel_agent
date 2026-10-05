# ============================================
# 智能旅行规划系统 · 全局配置
# 作用：集中读取 .env 中的环境变量，供全项目使用
# 原理：python-dotenv 把 .env 文件内容加载进 os.environ，
#       再用 os.getenv("KEY", 默认值) 读取，缺省给兜底默认值
# ============================================
import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR = backend/ 目录（本文件在 backend/app/config.py，向上两级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env：优先 backend/.env（项目专属），其次项目根 .env（学习阶段遗留，含 deepseek 等）
# load_dotenv 默认不覆盖已存在的环境变量，所以两处加载互不冲突
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


class Settings:
    """集中管理所有可配置项。初学者视角：就是一个"装着全部参数的盒子"。"""

    # ---------- 应用 ----------
    APP_NAME: str = "智能旅行规划系统"
    APP_VERSION: str = "0.1.0"
    # backend/ 目录（供各模块定位数据文件）
    BASE_DIR: str = str(Path(__file__).resolve().parent.parent)
    # 允许跨域的前端地址（Vue 开发服务器默认 5173；生产走 nginx 同源）
    CORS_ORIGINS: list = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ---------- 数据库（SQLite 存长期业务数据：用户保存的行程） ----------
    # 路径固定为 backend/data/travel.db，首次启动自动创建
    DATABASE_URL: str = f"sqlite:///{Path(BASE_DIR) / 'data' / 'travel.db'}"

    # ---------- Redis（缓存层：天气/地图/RAG 短期结果） ----------
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # 所有缓存 key 统一加前缀，避免与其他应用冲突
    REDIS_KEY_PREFIX: str = "trip_planner"
    # 默认缓存过期时间（秒）：天气/POI 这类数据 6 小时内基本不变
    REDIS_TTL_DEFAULT: int = int(os.getenv("REDIS_TTL_DEFAULT", "21600"))

    # ---------- LLM：deepseek-flash（OpenAI 兼容 + 原生多模态） ----------
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL_ID: str = os.getenv("DEEPSEEK_MODEL_ID", "deepseek-flash")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_TEMPERATURE: float = 0.7

    # ---------- 高德地图（需要你在 lbs.amap.com 注册后填写） ----------
    AMAP_WEB_KEY: str = os.getenv("AMAP_WEB_KEY", "")   # 后端：天气/地理编码/POI/路线
    AMAP_JS_KEY: str = os.getenv("AMAP_JS_KEY", "")     # 前端：地图渲染
    AMAP_BASE_URL: str = "https://restapi.amap.com/v3"

    # ---------- 嵌入模型（Chroma RAG 向量化用；复用旧项目 EMBED 配置） ----------
    EMBED_MODEL_TYPE: str = os.getenv("EMBED_MODEL_TYPE", "dashscope")
    EMBED_API_KEY: str = os.getenv("EMBED_API_KEY", "")
    EMBED_BASE_URL: str = os.getenv("EMBED_BASE_URL", "")
    EMBED_MODEL_NAME: str = os.getenv("EMBED_MODEL_NAME", "text-embedding-v3")

    # ---------- 重排序模型（RAG 精排，可选，缺省跳过） ----------
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "")

    # ---------- RAG 向量库 ----------
    CHROMA_DIR: str = str(Path(BASE_DIR) / "data" / "chroma_db")  # Chroma 本地持久化目录
    CHROMA_COLLECTION: str = "travel_guides"
    RAG_TOP_K: int = 4        # 检索返回条数
    RERANK_TOP_K: int = 3     # 重排序后保留条数


# 实例化一次，全项目共享（from config import settings）
settings = Settings()
