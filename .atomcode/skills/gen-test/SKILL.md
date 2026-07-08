---
name: gen-test
description: 为 rare-dx 新增的 Agent/路由生成 pytest 测试骨架，遵循现有 test_agents.py / test_golden.py 模式
disable_model_invocation: false
user_invocable: true
---

# gen-test · 测试骨架生成器

为 rare-dx 项目新增的 Agent（`app/agents/*.py`）或 API 路由（`app/api/*.py`）生成配套 pytest 测试。

## 触发场景
- AtomCode 新增 Agent 后自动建议生成测试
- 用户输入 `/gen-test <模块路径>` 手动触发

## 工作流

1. 读取目标模块，提取公开函数签名（`run` / `run_with_knows` / `_extract_*`）
2. 在 `tests/` 下创建 `test_<模块名>.py`，骨架含：
   - `import pytest`, `pytest.mark.asyncio`
   - 对每个 `run_with_knows` 函数：mock `KnowsClient` + `LLMGateway`，断言返回结构
   - 对 `run` 同步函数：构造 dict state，断言 key 存在
3. 若是 Agent，额外在 `tests/golden/` 下创建 `expected.json` 占位（{}），并在 `tests/test_golden.py` 追加一条回归用例
4. 运行 `pytest tests/test_<模块名>.py -v` 验证可收集

## 约定
- 测试文件命名：`test_<模块名>.py`（如 `test_phenotype_analyzer.py`）
- 用 `pytest.mark.asyncio` + `asyncio-mode=auto`
- Mock LLM/KnowS 失败路径，不只测 happy path
- 不要编造 HPO ID（参考 `data/hpo_frequency/orphanet_freq.json` 验证）

## 模板

```python
"""Tests for app/agents/<module>.py"""
import pytest
from app.agents import <module>

@pytest.mark.asyncio
async def test_run_with_knows_mocked(monkeypatch):
    # mock KnowsClient.search_single_source → []
    # mock LLMGateway.chat_json → {"phenotypes": []}
    state = {"current_user_message": "test", "session_id": "t"}
    result = await <module>.run_with_knows(state, knows, llm_gw)
    assert "phenotype_profile" in result  # 或对应键

def test_run_sync():
    state = {"current_user_message": "test", "session_id": "t"}
    result = <module>.run(state)
    assert isinstance(result, dict)
```
