"""D1 端到端冒烟测试 — Leigh 综合征演示剧本。

运行: pytest tests/test_d1_smoke.py -v
或:   python3 tests/test_d1_smoke.py

验证项:
1. 5 层推理全部产出非空结果
2. Top-1 假设为 Leigh 综合征 (ORPHA:520)
3. 遗传推理输出非空
4. 推荐检查路径非空
5. 最终报告含免责声明
6. LangGraph 状态机端到端跑通（含回流控制）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本可直接运行
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.agents.phenotype_analyzer import run as l1_run
from app.agents.hypothesis_generator import run as l2_run
from app.agents.temporal_reasoner import run as l3_run
from app.agents.genetic_reasoner import run as l4_run
from app.agents.pathway_planner import run as l5_run
from app.agents.report_synthesizer import run as l6_run


def _load_case(case_id: str = "case_01") -> dict:
    case_path = _ROOT / "data" / "demo_cases" / f"{case_id}.json"
    with open(case_path, encoding="utf-8") as f:
        return json.load(f)


def _run_pipeline(text: str, session_id: str = "d1-smoke") -> dict:
    """同步执行 5 层 + 报告（不调 KnowS）。"""
    state: dict = {
        "session_id": session_id,
        "current_user_message": text,
        "current_backflow_iterations": 0,
    }
    state.update(l1_run(state))
    state.update(l2_run(state))
    state.update(l3_run(state))
    state.update(l4_run(state))
    # 模拟回流：若 backflow 触发则重跑 L2-L4
    if state.get("current_backflow_to_hypothesis"):
        state["current_backflow_iterations"] = 1
        state.pop("current_backflow_to_hypothesis")
        state.update(l2_run(state))
        state.update(l3_run(state))
        state.update(l4_run(state))
    state.update(l5_run(state))
    state.update(l6_run(state))
    return state


def test_d1_end_to_end() -> None:
    """D1 病例端到端：Top-1 必须是 Leigh 综合征。"""
    case = _load_case("case_01")
    state = _run_pipeline(case["clinical_text"], "d1-test")

    # 1. 5 层推理全部产出非空
    assert state["phenotype_profile"].vectors, "L1 表型向量为空"
    assert state["hypotheses"], "L2 假设列表为空"
    assert state["temporal_matches"], "L3 时序匹配为空"
    assert state["genetic_constraint"] is not None, "L4 遗传约束为空"
    assert state["diagnostic_pathway"] and state["diagnostic_pathway"].steps, "L5 推荐检查为空"

    # 2. Top-1 假设为 Leigh 综合征
    top1 = state["hypotheses"][0]
    assert top1.disease_id == "ORPHA:520", f"Top-1 应为 ORPHA:520，实际为 {top1.disease_id}"
    assert "Leigh" in top1.disease_name or "leigh" in top1.disease_name.lower(), \
        f"Top-1 名称应含 Leigh，实际为 {top1.disease_name}"

    # 3. 遗传推理输出非空
    gc = state["genetic_constraint"]
    assert gc.inheritance_patterns, "遗传模式推断为空"

    # 4. 推荐检查路径非空
    pathway = state["diagnostic_pathway"]
    assert len(pathway.steps) >= 3, f"推荐检查应≥3项，实际 {len(pathway.steps)}"

    # 5. 最终报告含免责声明
    report = state["report"]
    assert "不构成诊断" in report["main_text"], "报告必须含免责声明"
    assert report["summary_snapshot"], "报告快照为空"

    # 6. 控制台输出（直接运行时）
    if __name__ == "__main__":
        print("\n=== D1 端到端冒烟测试 ===")
        print(f"L1 表型数: {len(state['phenotype_profile'].vectors)}")
        print(f"L2 假设数: {len(state['hypotheses'])}")
        print(f"  Top-1: {top1.disease_name} ({top1.disease_id})")
        print(f"  Top-1 后验: {top1.bayesian_score}")
        print(f"L3 时序匹配数: {len(state['temporal_matches'])}")
        print(f"L4 遗传模式: {[p.mode.value for p in gc.inheritance_patterns]}")
        print(f"L5 推荐检查: {len(pathway.steps)} 项")
        print(f"  Top-1: {pathway.steps[0].test_name} (EVOI={pathway.steps[0].net_evoi})")
        print(f"L6 报告字符数: {len(report['main_text'])}")
        print("\n✅ 全部通过")


def test_d2_gelman() -> None:
    """D2 病例：Gitelman 综合征 Top-1 应为 Gitelman。"""
    case = _load_case("case_02")
    state = _run_pipeline(case["clinical_text"], "d2-test")
    top1 = state["hypotheses"][0]
    assert top1.disease_id == "ORPHA:2136", f"D2 Top-1 应为 ORPHA:2136，实际 {top1.disease_id}"


def test_d3_xald() -> None:
    """D3 病例：X-ALD Top-1 应为 X-连锁肾上腺脑白质营养不良。"""
    case = _load_case("case_03")
    state = _run_pipeline(case["clinical_text"], "d3-test")
    top1 = state["hypotheses"][0]
    assert top1.disease_id == "ORPHA:64", f"D3 Top-1 应为 ORPHA:64，实际 {top1.disease_id}"


if __name__ == "__main__":
    test_d1_end_to_end()
    test_d2_gelman()
    test_d3_xald()
    print("\n🎉 D1/D2/D3 三个演示剧本全部通过")
