# 来源说明（Provenance）

本目录是第三方 Agent Skill 的 vendored 副本，用于为本项目提供**证据驱动的行程规划**参考规范。

| 项 | 值 |
|---|---|
| 上游仓库 | https://github.com/mrsunjc/TravelPilot-agent-skills |
| 提交 | `7fdde9abf62e984e76d898355967954136893ab2`（2026-08-08） |
| 许可 | MIT License —— 见同目录 `LICENSE`，Copyright (c) 2026 mrsunjc |
| 引入范围 | 仅上游 `travel-planner/` 目录 + `LICENSE`；**未**引入 `assets/`（17.8 MB README 截图）、`evals/`、`tools/`、`release/`、`tests/`（仓库级测试与发布脚本） |
| 是否修改 | 未做任何修改 |

## 与本项目的关系

- 同为**中文**旅行规划场景，且同样使用**高德** API（本 skill 读环境变量 `AMAP_API_KEY`，本项目配置项叫 `AMAP_WEB_KEY`）。
- `references/output-contract.md` 定义行程输出的结构契约；`schemas/final-plan.schema.json` 定义结构化计划；`scripts/travel_quality/` 是确定性质量门与证据校验。
- 其核心纪律值得本项目借鉴：**价格与开放时间必须来自工具而非模型记忆，并注明来源与核验日期；无法确认的字段写「待核验」而非编造**——与本项目防幻觉设计同源。

## 使用注意

- 本 skill 要求输出「每段交通方式 / 距离 / 门到门时间」。这与本项目
  `backend/app/services/map_service.py::enrich_itinerary` 的既有决定**冲突**
  （该处注释：用户出发起点不确定，车程无实际参考价值，且可省一半高德请求）。
  **参考时不要照搬这一条。**
- `scripts/` 下的 Python 只依赖标准库，是独立脚本；本项目应用代码**不 import** 它们。

## 更新方式

从上游按上述范围重新拉取覆盖即可。
