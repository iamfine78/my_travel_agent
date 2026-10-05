# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

智能旅行规划系统（TravelPlanner）：对话式生成旅行行程。用户输入目的地/天数/预算/偏好（可上传图片），系统分四级城市策略生成结构化行程，补齐高德地图 POI 坐标与图片、天气预报、预算拆分，支持自然语言单日编辑、历史存储与 Markdown/PDF 导出。

技术栈：FastAPI + Pydantic（后端）、Vue3 + Vite（前端）、SQLite（长期业务数据）、Redis（短期缓存）、Chroma（RAG 向量库）、deepseek-flash（OpenAI 兼容 LLM，原生多模态）、高德 Web 服务（地理/POI/天气）。

**代码注释、提示词、前端 UI 均为中文**。新增代码请沿用中文注释与中文用户可见文案的风格；提示词中若要求 LLM 输出 JSON，需同时用 `response_format={"type":"json_object"}` 与 Pydantic 校验双重约束。

## 常用命令

开发环境为 Windows，虚拟环境在项目根 `.venv`（`Scripts/python.exe`），脚本统一加 `-X utf8` 避免中文编码问题。

```bash
# 一键启动后端（检查/拉起 Redis + 校验高德 Key + uvicorn 热重载）
powershell -ExecutionPolicy Bypass -File start.ps1   # Windows
bash start.sh                                        # Linux / macOS

# 手动启动后端（等价于 start.ps1 第 3 步，在 backend/ 目录下运行）
.venv/Scripts/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# 前端开发（Vite :5173，/api 自动代理到 :8000）
cd frontend && npm run dev
npm run build          # 生产构建

# 攻略入库到 Chroma（首次运行或攻略改动后；--force 强制重建）
.venv/Scripts/python.exe -X utf8 backend/scripts/build_vector_db.py [--force]

# 依赖安装
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

**测试**：`backend/tests/` 是 **pytest 离线单元/接口测试套件**（187 例，约 3 秒），全部不依赖网络 / LLM / Redis，用 `monkeypatch` 顶替外部依赖、用临时 SQLite 顶替真实库：

```bash
.venv/Scripts/python.exe -X utf8 -m pytest backend -q                       # 全量离线测试
$env:RUN_LIVE_TESTS=1; .venv/Scripts/python.exe -X utf8 -m pytest backend -m live   # 真实 LLM/高德集成测试
```

`conftest.py` 提供四个夹具：`sample_itinerary`（最小行程）、`tmp_storage`（临时 SQLite 且替换 `storage_service` 全局 engine/SessionLocal）、`fake_cache`（内存假 Redis）、`client`（已接临时库的 TestClient）。

**注意**：`backend/scripts/test_m*.py` 是里程碑验证脚本，**import 即执行**，不是 pytest 用例 —— `pytest.ini` 的 `norecursedirs` 已排除 `scripts/`，否则收集阶段就会触发 `SystemExit`。这些脚本多为 `TestClient` 打真实接口，`test_m*.py` 会消耗 LLM 额度：

```bash
.venv/Scripts/python.exe -X utf8 backend/scripts/test_m2.py            # 按里程碑划分的端到端脚本 test_m1..m5 / test_m2_edit
.venv/Scripts/python.exe -X utf8 backend/scripts/evaluate_rag_retrieval.py [--limit 3]   # RAG 指标：Top1/TopK 命中率、MRR、Noise Rate、跨城市污染
.venv/Scripts/python.exe -X utf8 backend/scripts/debug_rag_retrieval.py  # 打印 query / top-k / rerank_score / reasons
```

**Docker**：`docker compose up --build` 一键起前端(nginx:8080) + 后端(8000) + Redis，配置文件已齐（`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf`）。nginx 把 `/api` 反代到 `backend:8000`，等同开发期 Vite proxy。**注意**：前端高德 JS Key 是 Vite **构建期**从 `frontend/.env` 内联进产物的（`frontend/.dockerignore` 刻意不排除 `.env`），改 Key 后需 `docker compose build frontend`。

## 架构与数据流

一次 `POST /api/trip/plan`（`backend/app/services/trip_service.py:plan_trip`）的编排顺序：

1. **城市四级分流** `city_resolver_service.resolve_city` — 先用 `guide_catalog` 注册表规范化城市名（含别名/行政后缀），再由高德行政区接口判定：
   - **A 级**（6 个沉淀城市，有攻略）→ Query Rewrite → Chroma 检索 + LLM 精排 → 攻略增强生成
   - **B 级**（动态城市）→ 高德 POI 候选池 → LLM 只能输出池内 POI ID → **池外校验拒绝（防幻觉核心）**。候选池的跨城过滤优先按 **adcode** 判定（`place_candidate_service._adcode_ok`：直辖市比前 2 位、地级市/州比前 4 位、县级市比完整 6 位），POI 无 adcode 时回退城市名包含。**注意**：目标 adcode 由 `city_resolver_service` 解析，其中 `_pick_city_district` 必须挑与输入同名的**城市**条目——高德对「西安」会先返回吉林的「西安区」，盲取第一条会把城市判成不存在
   - **C 级**（资料不足）→ LLM 通用知识兜底，如实标注来源
   - **D 级**（省级输入）→ 直接拒绝，提示选具体城市
2. **LLM 生成** `agents/trip_planner_agent.py` — 输出严格 JSON，Pydantic `Itinerary` 校验；`mode="dynamic"` 时注入 POI ID 白名单约束
3. **高德补全** `map_service.enrich_itinerary` — 坐标/地址/图片/营业时间；**天气感知修正**把雨雪高温提示追加进 `tips`
4. **预算校准** `trip_service.normalize_budget` — LLM 给的五项和常与用户总预算对不上：偏差 ±5% 内不动，超出则用 `BudgetBreakdown.scaled_to` 按比例缩放，并把四舍五入零头补到最大项，保证和值精确
5. **组装 `PlanResponse`** — 含逐日天气、来源标注、本次请求分项 token 消耗

**双存储分工**：SQLite（`storage_service` + `models/db_models.py` 的 `TripRecord` 表）存用户主动保存的行程，长期保留；Redis（`cache_service`）缓存天气/地理编码/POI/路线/RAG 结果，`trip_planner` 前缀 + TTL，**Redis 不可用时优雅降级**（不报错，直连上游）。

**RAG 链路**：`data/*.md` 攻略（景点写成 `###` 标题）→ `build_vector_db.py` 切块入库 Chroma → `rag/retriever.retrieve_and_rerank`（向量召回 top_k*2 → **三级精排** → 结果缓存）→ `format_context` 拼成提示词上下文。**检索按 `city` metadata 过滤**防止跨目的地污染；A 级空召回时 `fallback_candidates` 从攻略的 `###` 标题提取真实地名兜底。

**三级精排**（`rag/retriever.rerank`）：配置 `RERANK_MODEL` 时走 dashscope 专用 cross-encoder（端点形状由 `scripts/probe_rerank_api.py` 实测确认，非 OpenAI 兼容协议）→ 失败退 LLM 打分 → 再失败退规则打分。任一级失败都不影响出结果，只降排序质量。

**Token 观测**：`services/token_tracker.py` 进程级单例，按 `rewrite/rerank/planner/edit` 四阶段累计；`trip_service` 用前后快照差算本次请求增量，前端保存行程时把 `_token_usage` 一并写入 `itinerary_json` 长期保留，`GET /api/trip/stats` 汇总 session 与 saved 两路数据。

**前端**：Vue3 + vue-router（`views/Home|Result|History.vue`），`store.js` 是**纯内存**共享状态（规划结果、上传图片），刷新即失；所有后端调用集中在 `services/api.js`；`components/AmapTripMap.vue` 用高德 JS API 画路线与标记。（规划书里写的 `types/`、`api.ts`、`AmapTripMap` 的 TS 版本与实际不符，以实际 `.js` 代码为准。）

## 关键约定

- **配置**：`backend/app/config.py` 的 `Settings` 集中读 `.env`（先 `backend/.env` 后项目根 `.env`）。高德需 `AMAP_WEB_KEY`（后端）与 `AMAP_JS_KEY`（前端）两个 Key；参考 `backend/.env.example`。
- **新增沉淀城市**：在 `data/` 放 `{city}_guide.md`，并在 `rag/guide_catalog.py` 的 `GUIDE_CATALOG` 注册（含别名），然后重跑 `build_vector_db.py --force`。
- **接口层薄、服务层厚**：`api/routes/*.py` 只做参数校验与调用，业务编排放在 `services/`。业务失败抛 `app/core/errors.py` 里的 `PlanningError` 子类（`status_code` 写在异常类上），由 `api/main.py` 注册的 handler 统一映射成 HTTP 响应——**不要在各路由里重复 try/except 转状态码**。`HTTPException` 留给接口层自己发现的问题（如路径参数指向的记录不存在）。
- **注意路由顺序**：FastAPI 中静态路径必须定义在 `/{trip_id}` 之前（见 `export.py` 里 `from-data` 的注释），否则会被当作 path 参数吞掉。
- `skills/` 存放第三方 Agent Skill（目前 `frontend-design`、`travel-planner`）：是给 Claude 参考的规范文档，**不被应用代码 import**。其中 `travel-planner` 的来源、版本与「不可照搬之处」见 `skills/travel-planner/PROVENANCE.md`。
- `docs/智能旅行规划系统-项目规划书.md` 是早期规划文档，其中"命令行 travel_agent/ 目录"等结构**已废弃**，仅里程碑与设计意图仍有参考价值。
- 仓库已 git 初始化（`main` 分支）。`backend/.env` 含真实密钥且被 `.gitignore` 排除，**不要提交**；`data/chroma_db`、`data/travel.db`、`frontend/dist`、`scripts/_*` 均为可重新生成的产物，已忽略。
