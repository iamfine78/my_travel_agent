# scripts 目录索引

## ⚠️ 重要：这些脚本「直接运行」，不是 pytest 用例

本目录下的脚本**没有 `if __name__ == "__main__":` 守卫**，用 `import` 或 pytest 收集时会**立即执行**（发真实请求、打印、甚至写数据），例如 `test_m1.py` 在模块顶层就发请求并以 `sys.exit()` 结束——pytest 收集它们会导致 `INTERNALERROR`。

因此 `backend/pytest.ini` 用 `norecursedirs` 显式排除了 `scripts/`。**不要在 scripts 目录下跑 pytest**；要跑测试请用 `backend/tests/`。

正确用法一律是直接运行：

```bash
.venv\Scripts\python.exe -X utf8 backend/scripts/<脚本名>.py
```

## 脚本分类

### 入库 / 语料
| 脚本 | 用途 |
|---|---|
| `build_vector_db.py` | 把 `data/*.md` 切块向量化写入 Chroma（`--force` 强制重建） |
| `copy_env.py` | 从旧项目复制 `.env` 所需配置项 |

### 评估
| 脚本 | 用途 |
|---|---|
| `evaluate_rag_retrieval.py` | RAG 检索指标（Top1/Top3/MRR/Noise/Latency/跨城污染），用例见 `eval/` |
| `evaluate_itinerary_quality.py` | 行程质量评估 |
| `make_sample.py` | 生成示例行程（`manual_sample.pdf`） |

### 探针（先确认真实接口形状，再实现）
| 脚本 | 用途 |
|---|---|
| `probe_rerank_api.py` | dashscope 精排端点与请求/响应形状 |
| `probe_embed_api.py` / `probe_batch_embed.py` | 嵌入接口 |
| `probe_amap.py` | 高德接口 |
| `probe_openai_sdk.py` | OpenAI SDK 连通性 |

### 调试
| 脚本 | 用途 |
|---|---|
| `debug_rag_retrieval.py` | 打印 query / top-k / rerank_score / reasons |
| `debug_poi_name.py` / `debug_route.py` / `debug_route2.py` | 高德 POI 与路线调试 |

### 验证（针对具体修复的一次性核对）
`verify_b_fix.py`、`verify_enrich*.py`、`verify_open_time.py`、`verify_pdf.py`

### 里程碑 / 手工联调（**会调用真实外部服务并消耗额度**）
| 脚本 | 用途 |
|---|---|
| `test_m1.py` … `test_m5.py`、`test_m2_edit.py` | 按里程碑的端到端验证 |
| `test_b_level.py` | B 级动态城市候选池与白名单校验 |
| `test_playguide.py` / `test_refresh.py` / `test_token_stats.py` | 特定功能手工验证 |

> 这一组的共同特点：直接打真实接口、依赖 `.env` 里的密钥、会消耗 LLM 额度。

## 临时调试产物

以 `_` 开头的文件（`_debug_food.py`、`_probe_ot.py`、`_*_out.txt` 等）是过程性产物，已被 `.gitignore` 排除。你可以随时删除，不影响任何正式脚本。
