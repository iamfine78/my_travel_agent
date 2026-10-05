# 智能旅行规划系统 · TravelPlanner

对话式智能旅行规划系统：输入「去哪、玩几天、预算多少、什么偏好」（也可上传照片），自动生成包含每日行程、景点玩法、餐饮住宿、预算拆分、天气预报的完整行程单，支持自然语言改行程、历史留存与 Markdown / PDF 导出。

## 功能特性

- **四级城市策略**：A 级（有本地攻略，RAG 增强）／B 级（动态城市，高德候选池 + POI ID 白名单防幻觉）／C 级（资料不足，通用知识兜底并如实标注）／D 级（省级输入，提示选具体城市）
- **实时信息**：高德 POI 坐标 / 地址 / 图片 / 营业时间补全，逐日天气预报与出行提示
- **多模态**：上传照片 → deepseek-flash 视觉理解 → 纳入行程规划
- **自然语言编辑**：一句话修改某天行程（如「第二天换成轻松一点」）
- **历史与导出**：SQLite 长期存储，一键导出中文 Markdown / PDF
- **Token 观测**：按「改写 / 重排 / 生成 / 编辑」四阶段统计消耗

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Pydantic + SQLAlchemy（SQLite） |
| 前端 | Vue3 + Vite + vue-router + Axios |
| LLM | deepseek-flash（OpenAI 兼容，原生多模态） |
| RAG | Chroma 向量库 + LLM 精排（deepseek-flash） |
| 缓存 | Redis（不可用时优雅降级） |
| 外部服务 | 高德地图 Web 服务（POI / 地理编码 / 天气） |

## 目录结构

```
pythonProject2/
├── backend/
│   ├── app/
│   │   ├── agents/       # LLM 行程生成与单日编辑、RAG Query Rewrite
│   │   ├── api/          # FastAPI 入口与路由（trip / export / weather）
│   │   ├── models/       # Pydantic 请求响应模型、SQLAlchemy 表
│   │   ├── rag/          # 攻略目录、Chroma 入库检索、精排、一致性校验
│   │   ├── services/     # 行程编排、城市分级、高德、天气、存储、缓存、导出
│   │   └── config.py     # 全局配置（读 .env）
│   ├── data/             # 6 城攻略 md、检索规则、Chroma / SQLite（运行时生成）
│   ├── eval/             # RAG 评估样例集
│   └── scripts/          # 入库、调试、评估脚本
├── frontend/src/         # Home / Result / History 三页面 + 高德地图组件
├── docs/                 # 项目文档
├── docker-compose.yaml   # 编排（注意：Dockerfile 尚未提供）
└── start.ps1             # Windows 一键启动脚本
```

## 快速开始

### 前置条件

- Python 3.10+（开发环境实测 3.14）
- Node.js 18+（实测 24）
- Redis（Windows 可用原生版；也可用 docker-compose 的 redis 服务）
- [高德开放平台](https://lbs.amap.com/) 个人开发者 Key（Web 服务 Key + Web 端 JS Key 各一个）

### 1. 配置环境变量

复制模板并填写：

```bash
cp backend/.env.example backend/.env
```

需要填写的键：`DEEPSEEK_API_KEY`、`AMAP_WEB_KEY`、`AMAP_JS_KEY`、`EMBED_API_KEY`（向量化用）。

> `.env` 含真实密钥，已被 `.gitignore` 排除，切勿提交。

### 2. 安装依赖

```bash
# 后端（虚拟环境位于项目根 .venv）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

# 前端
cd frontend && npm install
```

### 3. 攻略入库（首次运行必做）

```bash
.venv/Scripts/python.exe -X utf8 backend/scripts/build_vector_db.py
```

### 4. 启动

```bash
# 后端：自动拉起 Redis + 校验高德 Key + uvicorn 热重载（Windows PowerShell）
powershell -ExecutionPolicy Bypass -File start.ps1

# 前端（另开终端）
cd frontend && npm run dev
```

- 前端：http://localhost:5173
- 后端 API 文档：http://127.0.0.1:8000/docs

## 常用命令

```bash
# 后端手动启动（等价于 start.ps1 第 3 步，在 backend/ 目录下）
.venv/Scripts/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# 前端生产构建
cd frontend && npm run build

# 里程碑端到端验证脚本（会调用真实 LLM）
.venv/Scripts/python.exe -X utf8 backend/scripts/test_m2.py

# RAG 检索效果评估（Top1/TopK 命中率、MRR、Noise Rate、跨城市污染）
.venv/Scripts/python.exe -X utf8 backend/scripts/evaluate_rag_retrieval.py --limit 3

# 后端单元/接口测试（pytest，离线，无需任何 Key）
.venv/Scripts/python.exe -X utf8 -m pytest backend -q

# 真实 LLM/高德集成测试（默认跳过，会消耗额度）
RUN_LIVE_TESTS=1 .venv/Scripts/python.exe -X utf8 -m pytest backend -m live
```

> `backend/tests/` 为 pytest 测试套件（离线，用 monkeypatch / 临时 SQLite / 假 Redis 隔离外部依赖）；
> `backend/scripts/` 下的 `test_m*.py` 是「直接运行」的里程碑验证脚本，不是 pytest 用例。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/trip/plan` | 生成行程（含图片多模态） |
| POST | `/api/trip/{id}/edit` | 自然语言编辑某天 |
| POST | `/api/trip/{id}/refresh` | 补全旧行程的地理信息 |
| GET | `/api/trip/history` | 历史列表 |
| GET | `/api/trip/{id}` | 行程详情 |
| DELETE | `/api/trip/{id}` | 删除行程 |
| GET | `/api/trip/stats` | Token 观测汇总 |
| POST | `/api/export/from-data?format=md\|pdf` | 导出当前行程 |
| GET | `/api/weather/{city}` | 城市天气 |

完整交互式文档见 `/docs`。

## 文档

- [项目规划书](docs/智能旅行规划系统-项目规划书.md)

## 开发约定

- 代码注释、提示词、UI 文案均为中文
- LLM 输出统一用 `response_format=json_object` + Pydantic 双重校验
- 接口层（`api/routes`）只做校验与异常转换，业务编排在 `services/`
- 新增沉淀城市：在 `backend/data/` 放 `{city}_guide.md`，在 `rag/guide_catalog.py` 注册并重跑入库脚本
