---
name: api-documenter
description: rare-dx API 文档同步子代理 — FastAPI 路由 OpenAPI + 前端 api.ts 类型对齐
disable_model_invocation: false
user_invocable: true
---

# api-documenter · API 文档同步器

为 rare-dx 的 FastAPI 路由生成/同步 OpenAPI 文档，并检查前端 `api.ts` 类型对齐。

## 触发场景
- `app/api/routes.py` 或 `app/api/agent_routes.py` 变更后
- 用户输入 `/api-doc` 手动触发

## 工作流

1. 扫描 `app/api/*.py` 的 `@router.get/post` 装饰器，提取：
   - 路径、方法、query/params 参数
   - 返回类型（`EventSourceResponse` / `JSONResponse` / `Response`）
2. 对比 `frontend/src/lib/api.ts` 的 `fetchSSE` / `fetch` 调用：
   - 路径是否一致
   - 参数名是否匹配（如 `user_message` vs `userMessage`）
   - SSE 事件名是否与后端 `push(event_type, ...)` 一致
3. 更新 `docs/API.md`（若存在）或提示创建：
   - 端点表（方法/路径/说明/事件类型）
   - SSE 事件类型表

## rare-dx 现有端点（基线）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 健康检查 |
| GET | /api/diagnostic/stream | SSE 流式诊断 |
| GET | /api/report/download | 下载 DOCX/PDF |
| GET | /api/sessions | 会话列表 |
| GET | /api/sessions/{id} | 会话详情 |
| DELETE | /api/sessions/{id} | 删除会话 |
| GET | /api/sessions/{id}/audit | 审计日志 |

SSE 事件（12 种）：`round_start` / `agent_start` / `agent_delta` / `agent_done` / `phenotype_vector` / `hypothesis_ranking` / `temporal_match` / `inheritance_pattern` / `evoi_recommendation` / `report_delta` / `evidence` / `safety_valve` / `round_end` / `error`

## 输出
- 端点变更 diff（后端 vs 前端 vs docs）
- 不一致项清单（路径/参数名/事件名）
- 不自动改前端，只报告（前端改动由主代理执行）
